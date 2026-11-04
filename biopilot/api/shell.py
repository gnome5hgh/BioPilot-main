"""网页终端的面板会话：每个用户一条持久 shell，跨对话/跨面板开关复用。

为什么需要这一层：终端面板可以在任意会话里打开，关闭面板不应杀掉 shell；用户下次
再打开时要看到上次的输出并继续操作。因此 shell 进程挂在服务端、按 user_id 复用，
WS 只是「附着/脱离」，输出进环形缓冲，重连时先回放再继续。

安全边界：这是**宿主 shell**（拥有服务进程的操作系统权限），不是 agent 工具。是否
启用由 ``runtime.allow_host_shell`` 显式控制，默认关闭；启用前必须接受服务账号的
文件与环境暴露风险。子进程环境只保留终端必需的白名单变量，不把 API key/DSN 带进去。
"""
from __future__ import annotations

import asyncio
import codecs
import fcntl
import json
import os
import pty
import struct
import termios
import time
from pathlib import Path
from typing import Any

__all__ = ["ShellSession", "ShellManager"]

#: 每个用户保留的输出回放上限（超出从头部丢弃，避免无限占用内存）
BUFFER_LIMIT = 256 * 1024

#: 无客户端附着多久后回收 shell（秒）
IDLE_SECONDS = 30 * 60

#: 允许带进 shell 的环境变量白名单：终端能跑起来所需的最小集合。
#: BIOPILOT_*/API key/DSN/云凭证一律不带，避免 `env` 直接读走密钥。
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
    async def start(cls, user_id: str, cwd: Path, manager: "ShellManager") -> "ShellSession":
        """启动一条新 shell（PTY + 交互式进程），并开始读输出。"""
        master, slave = pty.openpty()
        env = {key: value for key, value in os.environ.items() if key in _ENV_WHITELIST}
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
                    chunk = await loop.run_in_executor(None, os.read, self.master, 8192)
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
            await loop.run_in_executor(None, os.write, self.master, data.encode("utf-8"))
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
                session = await ShellSession.start(user_id, Path.home(), self)
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
