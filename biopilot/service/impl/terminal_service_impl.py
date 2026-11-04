"""网页终端实现：每个用户一条持久 shell，跨对话/跨面板开关复用。"""
from __future__ import annotations

import asyncio
import codecs
import fcntl
import json
import os
import pathlib
import pty
import struct
import termios
import time
from pathlib import Path
from typing import Any

from biopilot.common.utils.env import os_env
from biopilot.domain.terminal_socket import TerminalSocket
from biopilot.service.errors import ForbiddenError
from biopilot.service.terminal_service import TerminalService

#: 每个用户保留的输出回放上限（超出从头部丢弃，避免无限占用内存）
BUFFER_LIMIT = 256 * 1024

#: 无客户端附着多久后回收 shell（秒）
IDLE_SECONDS = 30 * 60

#: 允许带进 shell 的环境变量白名单：终端能跑起来所需的最小集合。
_ENV_WHITELIST = {
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR",
    "USER", "LOGNAME", "SHELL", "TERM", "COLORTERM",
    "XDG_DATA_DIRS", "XDG_CONFIG_HOME", "XDG_CACHE_HOME",
}


def _shell_command() -> str:
    """选择用户默认 shell；环境未声明时按平台回退。"""
    shell = os.environ.get("SHELL") or ""
    if shell and Path(shell).exists():
        return shell
    for candidate in ("/bin/zsh", "/bin/bash", "/bin/sh"):
        if Path(candidate).exists():
            return candidate
    return "/bin/sh"


def _child_setup() -> None:
    """子进程成为会话首进程并取得控制终端（shell 的作业控制需要）。"""
    os.setsid()
    try:
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    except OSError:
        pass


class ShellSession:
    """一条 PTY shell 会话：进程、输出缓冲与当前附着的 WebSocket。

    Attributes:
        user_id: 归属用户（一个用户一条会话）
        master: PTY 主端 fd
        proc: shell 子进程
        buffer: 输出回放缓冲（字节）
        clients: 当前附着的 websocket 集合
        last_active: 最后一次附着时刻（回收判定）
        closed: 进程是否已结束
    """

    def __init__(self, user_id: str, master: int, proc: Any):
        self.user_id = user_id
        self.master = master
        self.proc = proc
        self.buffer = bytearray()
        self.clients: set[Any] = set()
        self.last_active = time.monotonic()
        self.closed = False
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._reader: asyncio.Task | None = None
        self.manager: ShellManager | None = None

    @classmethod
    async def start(cls, user_id: str, cwd: Path,
                    manager: "ShellManager") -> "ShellSession":
        """启动一条新 shell（PTY + 交互式进程），并开始读输出。"""
        master, slave = pty.openpty()
        env = {key: value for key, value in os.environ.items()
               if key in _ENV_WHITELIST}
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        proc = await asyncio.create_subprocess_exec(
            _shell_command(),
            stdin=slave, stdout=slave, stderr=slave,
            cwd=str(cwd), env=env, preexec_fn=_child_setup,
        )
        os.close(slave)
        session = cls(user_id=user_id, master=master, proc=proc)
        session.manager = manager
        session._reader = asyncio.create_task(session._read_loop())
        return session

    async def _read_loop(self) -> None:
        """持续读 PTY 输出：写入环形缓冲并广播给所有附着客户端。"""
        loop = asyncio.get_running_loop()
        try:
            while True:
                try:
                    chunk = await loop.run_in_executor(
                        None, os.read, self.master, 8192)
                except OSError:
                    break
                if not chunk:
                    break
                self.buffer.extend(chunk)
                if len(self.buffer) > BUFFER_LIMIT:
                    del self.buffer[: len(self.buffer) - BUFFER_LIMIT]
                text = self._decoder.decode(chunk)
                if text:
                    await self.broadcast(text)
        finally:
            self.closed = True
            await self.broadcast("\r\n[终端进程已退出]\r\n")
            try:
                self.proc.terminate()
            except Exception:
                pass
            try:
                os.close(self.master)
            except OSError:
                pass
            if self.manager is not None:
                self.manager.forget(self)

    async def broadcast(self, text: str) -> None:
        """把文本发给所有附着客户端；发送失败的客户端就地移除。"""
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:
                self.clients.discard(ws)

    def replay(self) -> str:
        """返回当前缓冲的可回放文本（重连时先写这个）。"""
        return bytes(self.buffer).decode("utf-8", errors="replace")

    async def write(self, data: str) -> None:
        """把客户端输入写进 PTY。"""
        if self.closed or not data:
            return
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, os.write, self.master, data.encode("utf-8"))
        except OSError:
            pass

    def resize(self, cols: int, rows: int) -> None:
        """调整 PTY 窗口尺寸（影响换行与全屏程序）。"""
        try:
            packed = struct.pack("HHHH", max(1, rows), max(1, cols), 0, 0)
            fcntl.ioctl(self.master, termios.TIOCSWINSZ, packed)
        except OSError:
            pass

    def kill(self) -> None:
        """结束 shell 并关闭 PTY（重启/回收时用）。"""
        self.closed = True
        try:
            self.proc.terminate()
        except Exception:
            pass
        try:
            os.close(self.master)
        except OSError:
            pass


class ShellManager:
    """按 user_id 管理持久 shell：附着、脱离、重启与空闲回收。"""

    def __init__(self):
        self._sessions: dict[str, ShellSession] = {}
        self._lock = asyncio.Lock()

    async def attach(self, user_id: str, ws: Any) -> ShellSession:
        """取该用户的 shell（不存在就启动），把 ws 附着上去并回放历史输出。"""
        async with self._lock:
            session = self._sessions.get(user_id)
            if session is None or session.closed:
                session = await ShellSession.start(
                    user_id, Path.home(), self)
                self._sessions[user_id] = session
            session.clients.add(ws)
            session.last_active = time.monotonic()
            replay = session.replay()
        if replay:
            await ws.send_text(replay)
        return session

    def detach(self, session: ShellSession, ws: Any) -> None:
        """WS 断开只脱离，不杀 shell——下次打开继续。"""
        session.clients.discard(ws)
        session.last_active = time.monotonic()

    def forget(self, session: ShellSession) -> None:
        """进程结束后从注册表移除（仅当仍是当前实例）。"""
        if self._sessions.get(session.user_id) is session:
            self._sessions.pop(session.user_id, None)

    async def restart(self, user_id: str) -> bool:
        """结束并移除该用户的 shell；下一次附着会启动新进程。"""
        async with self._lock:
            session = self._sessions.pop(user_id, None)
        if session is not None:
            session.kill()
            return True
        return False

    async def close_idle(self) -> None:
        """回收长时间无人附着的 shell。"""
        now = time.monotonic()
        for user_id, session in list(self._sessions.items()):
            if session.clients:
                continue
            if now - session.last_active < IDLE_SECONDS:
                continue
            self._sessions.pop(user_id, None)
            session.kill()

    async def reaper(self) -> None:
        """后台循环：每分钟回收一次空闲 shell。"""
        while True:
            await asyncio.sleep(60)
            try:
                await self.close_idle()
            except Exception:
                pass

    async def shutdown(self) -> None:
        """停服时结束所有 shell（含缓冲与子进程）。"""
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.kill()


class TerminalServiceImpl(TerminalService):
    """终端面板服务：配置、重启与 WebSocket 会话。"""

    def __init__(self):
        self._manager = ShellManager()

    def config(self) -> dict:
        """返回当前部署是否启用宿主终端（前端据此决定按钮是否可用）。"""
        from biopilot.config import BioPilotConfig
        cfg = BioPilotConfig.from_env()
        shell = os_env("SHELL", "/bin/sh") or "/bin/sh"
        return {
            "enabled": bool(cfg.runtime.allow_host_shell),
            "shell": pathlib.Path(shell).name,
        }

    async def restart(self, user_id: str) -> dict:
        """结束该用户当前的 shell；下一次打开面板会启动新进程。"""
        from biopilot.config import BioPilotConfig
        if not BioPilotConfig.from_env().runtime.allow_host_shell:
            raise ForbiddenError("当前部署未启用宿主终端")
        restarted = await self._manager.restart(user_id)
        return {"status": "restarted" if restarted else "no-session"}

    async def run_websocket(self, ws: TerminalSocket) -> None:
        """终端 WebSocket：附着到该用户的持久 shell，断线只脱离不杀进程。"""
        x_user_id = ws.headers.get("x-user-id", "")
        if not x_user_id:
            await ws.close(code=1008, reason="缺少 X-User-Id 请求头")
            return
        from biopilot.config import BioPilotConfig
        if not BioPilotConfig.from_env().runtime.allow_host_shell:
            await ws.close(code=1008, reason="当前部署未启用宿主终端")
            return
        await ws.accept()
        try:
            session = await self._manager.attach(x_user_id, ws)
        except Exception:
            await ws.close(code=1011, reason="终端启动失败")
            return
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    payload = json.loads(raw)
                except (TypeError, ValueError):
                    payload = None
                if isinstance(payload, dict) and payload.get("type") == "input":
                    await session.write(str(payload.get("data") or ""))
                elif isinstance(payload, dict) and payload.get("type") == "resize":
                    try:
                        session.resize(int(payload.get("cols") or 0),
                                       int(payload.get("rows") or 0))
                    except (TypeError, ValueError):
                        pass
                elif payload is None:
                    # 兼容旧客户端：纯文本即键盘输入
                    await session.write(raw)
        except Exception:
            # 客户端关闭/网络断开：只脱离，保留 shell 供下次继续
            pass
        finally:
            self._manager.detach(session, ws)

    async def reaper(self) -> None:
        """后台回收空闲 shell。"""
        await self._manager.reaper()

    async def shutdown(self) -> None:
        """停服时结束所有 shell。"""
        await self._manager.shutdown()
