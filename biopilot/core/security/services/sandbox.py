"""沙箱执行能力：把一段 Python 代码放进一次性容器里跑。

这是安全模块的**独立防护能力**（与命令解析同层同角色）——不是
中间件洋葱的一部分，而是「执行一段代码」这个动作本身的实现，由工具直接调用。

边界由**容器**强制，不是进程内的字符串检查：默认断网、宿主目录以只读挂载进去、
只开一个临时目录可写；容器另加一套固定加固（根文件系统只读、丢弃全部
capability、禁止提权、内存与 CPU 与进程数上限、以非 root 运行）。宿主其余部分
（home、代码仓库、配置文件）根本不进容器。

环境不可用（Docker 不可执行、镜像不存在）时抛 ``SandboxUnavailable``——**fail
closed**：宁可拒绝执行，也绝不退回进程内裸跑。这条没有开关。

本模块不读配置：政策由调用方（工具）组装好传进来，保持与配置解耦。
"""

import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

#: 待执行脚本在容器内的工作目录与文件名——代码先落到临时目录再执行，
#: 使每次跑的脚本本身留在磁盘上可回溯（不入镜像、不经 stdin）。
_WORKDIR = "/work"
_SCRIPT_NAME = "_run.py"
_SCRIPT_IN_CONTAINER = f"{_WORKDIR}/{_SCRIPT_NAME}"

#: 容器内运行代码的用户（镜像里建的非 root 用户，非 POSIX 平台的回退值）
_SANDBOX_USER = "sandbox"


def _container_user() -> str:
    """返回容器内运行用户。

    优先用宿主进程的 uid:gid：临时目录由宿主创建，容器内换用另一个固定 uid
    会在宿主 uid 不同（Linux 部署、root 进程）时因目录属主不符而不可写，整次
    执行以 PermissionError 收场。沿用宿主 uid 还能让产物文件直接归调用者所有。
    """
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if getuid is None or getgid is None:
        return _SANDBOX_USER
    return f"{getuid()}:{getgid()}"


@dataclass(frozen=True)
class SandboxPolicy:
    """一次沙箱执行的政策快照。

    调用方（工具）按配置组装：镜像、只读挂载、可写临时目录、资源上限、超时。
    加固项不在此暴露——它们是代码里的固定策略，没有关掉的入口。

    Attributes:
        image: str，沙箱镜像名（须预先构建）
        read_mounts: tuple[tuple[str, str], ...]，只读挂载 (宿主绝对路径, 容器内路径)
        scratch: str，宿主可写临时目录（挂载到容器内 ``/work``）
        network: bool，容器是否联网（默认 False = 断网）
        memory: str，内存上限（docker ``--memory`` 语法，如 "2g"）
        cpus: float，CPU 上限
        pids_limit: int，进程数上限
        timeout_s: int，单次执行超时（秒）
    """

    image: str
    scratch: str
    read_mounts: tuple[tuple[str, str], ...] = ()
    network: bool = False
    memory: str = "2g"
    cpus: float = 2.0
    pids_limit: int = 128
    timeout_s: int = 60


@dataclass
class SandboxResult:
    """一次沙箱执行的结果。

    Attributes:
        exit_code: int，进程退出码（超时时为 -1）
        stdout: str，标准输出全文
        stderr: str，标准错误全文
        timed_out: bool，是否因超时被终止
        duration_ms: int，从起容器到结束的耗时（毫秒）
        files: list[dict]，临时目录里本次新产生的文件 ``[{"name", "size"}]``
    """

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int
    files: list[dict] = field(default_factory=list)


class SandboxUnavailable(Exception):
    """沙箱环境不可用（Docker 不可执行或镜像缺失）。

    这是 fail-closed 的表达：调用方据此返回可行动的错误文本，**绝不**退回
    进程内执行代码。
    """


def _docker(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    """执行一次 docker 子命令——**全模块唯一真正起进程的地方**。

    可用性探测、镜像检查、起容器、超时后杀容器都经这里，测试只需在此处替换
    即可覆盖全部 docker 交互（接缝只此一个）。

    Args:
        args: list[str]，docker 子命令与参数（不含开头的 "docker"）
        timeout: float，子进程超时（秒）

    Returns:
        subprocess.CompletedProcess，含 returncode / stdout / stderr。

    Raises:
        OSError: docker 可执行文件不存在（交由调用方转 SandboxUnavailable）。
        subprocess.TimeoutExpired: 子进程超时。
    """
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout)


def build_docker_argv(policy: SandboxPolicy, container_name: str) -> list[str]:
    """把政策拼成 ``docker`` 的参数表（安全关键，纯函数便于断言）。

    这里决定墙长什么样：断网、根只读、丢权限、禁提权、资源上限、非 root、
    只读挂载、唯一可写目录。改动本函数即改动安全边界。

    Args:
        policy: SandboxPolicy，本次执行政策
        container_name: str，容器名（超时后据此杀容器）

    Returns:
        list[str]，``docker`` 之后的完整参数（不含开头的 "docker"）。
    """
    argv = ["run", "--rm", "--name", container_name]

    # 网络：默认断网（--network none）。容器内没有出口，注入带偏的代码也传不出去。
    argv += ["--network", "bridge" if policy.network else "none"]

    # 文件系统：根只读，只给 /tmp 一个内存文件系统；可写面只有显式挂载的临时目录。
    argv += ["--read-only", "--tmpfs", "/tmp"]

    # 权限：丢光 capability + 禁止提权，阻断容器内的越权路径。
    argv += ["--cap-drop", "ALL", "--security-opt", "no-new-privileges"]

    # 资源：内存 / CPU / 进程数三道上限，防跑飞拖死宿主。
    argv += ["--memory", policy.memory, "--cpus", str(policy.cpus),
             "--pids-limit", str(policy.pids_limit)]

    # 非 root：用宿主 uid:gid 落地，既不以 root 运行，也保证挂载目录可写。
    argv += ["--user", _container_user(), "-e", "HOME=/tmp", "-e", "USER=sandbox"]

    # 只读挂载：宿主目录接进容器后不可写。
    for host_path, container_path in policy.read_mounts:
        argv += ["-v", f"{host_path}:{container_path}:ro"]

    # 唯一可写挂载：临时目录。
    argv += ["-v", f"{policy.scratch}:{_WORKDIR}:rw"]

    argv += ["-w", _WORKDIR, policy.image, "python", _SCRIPT_IN_CONTAINER]
    return argv


def _ensure_available(policy: SandboxPolicy) -> None:
    """确认 docker 可执行且镜像存在，否则抛 SandboxUnavailable。

    Args:
        policy: SandboxPolicy，至少用到 image

    Raises:
        SandboxUnavailable: docker 不可执行（不存在 / 无权限）或镜像不存在。
    """
    try:
        proc = _docker(["image", "inspect", policy.image], timeout=30)
    except OSError as e:
        raise SandboxUnavailable(
            f"docker 不可执行（{e}）；沙箱代码执行已禁用，请先安装并启动 Docker"
        )
    except subprocess.TimeoutExpired:
        raise SandboxUnavailable("docker 无响应（image inspect 超时）；请检查 Docker 是否在运行")
    if proc.returncode != 0:
        raise SandboxUnavailable(
            f"沙箱镜像 '{policy.image}' 不存在；请先构建它"
            f"（docker build -f docker/sandbox.Dockerfile -t {policy.image} .）"
        )


def _kill(container_name: str) -> None:
    """尽力杀掉超时容器（失败静默——容器已 --rm，坏情况也只是多留一个）。"""
    try:
        _docker(["kill", container_name], timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """临时目录快照：相对路径 → (大小, mtime_ns)，用于识别本次新产生的文件。"""
    snap: dict[str, tuple[int, int]] = {}
    for p in root.rglob("*"):
        if p.is_file():
            st = p.stat()
            snap[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns)
    return snap


def _diff_files(root: Path, before: dict[str, tuple[int, int]]) -> list[dict]:
    """本次新增或改动的文件清单（脚本自身不算产物）。"""
    out: list[dict] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root))
        if rel == _SCRIPT_NAME:
            continue
        st = p.stat()
        if before.get(rel) != (st.st_size, st.st_mtime_ns):
            out.append({"name": rel, "size": st.st_size})
    return out


def run_python(code: str, policy: SandboxPolicy) -> SandboxResult:
    """在一次性容器里执行一段 Python 代码，返回结果。

    代码先落到临时目录的脚本文件再执行（一次跑完容器即删），超时按容器名杀掉。
    环境不可用时抛 SandboxUnavailable——不返回降级结果、不退回进程内。

    Args:
        code: str，要执行的 Python 源码
        policy: SandboxPolicy，本次执行政策

    Returns:
        SandboxResult，退出码 / 输出 / 是否超时 / 耗时 / 本次产物清单。

    Raises:
        SandboxUnavailable: docker 不可执行或镜像不存在（fail-closed）。
    """
    _ensure_available(policy)

    scratch = Path(policy.scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / _SCRIPT_NAME).write_text(code, encoding="utf-8")
    # 脚本落盘后再拍快照——脚本本身不算产物（_diff_files 亦二次排除）。
    before = _snapshot(scratch)

    container_name = f"biopilot-sbx-{uuid.uuid4().hex[:12]}"
    argv = build_docker_argv(policy, container_name)

    started = time.monotonic()
    timed_out = False
    try:
        # 子进程超时留出余量：真正的时间上限由容器自身承担，这里是兜底。
        proc = _docker(argv, timeout=float(policy.timeout_s) + 15.0)
        exit_code = proc.returncode
        stdout, stderr = proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill(container_name)
        exit_code, stdout, stderr = -1, "", f"执行超时（{policy.timeout_s}s），容器已被终止"
    except OSError as e:
        raise SandboxUnavailable(f"docker 执行失败（{e}）")

    duration_ms = int((time.monotonic() - started) * 1000)
    return SandboxResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        duration_ms=duration_ms,
        files=_diff_files(scratch, before),
    )


def docker_available() -> bool:
    """docker 是否可执行（启动预检用；不起容器、不校验镜像）。

    Returns:
        True 表示 docker 命令可执行；False 表示不存在或无权限。
    """
    return shutil.which("docker") is not None


def image_present(image: str) -> bool:
    """沙箱镜像是否已构建（启动预检用）。

    Docker 不可执行或镜像不存在都返回 False——预期失败不抛异常。

    Args:
        image: str，镜像名

    Returns:
        True 表示镜像存在；False 表示 docker 不可用或镜像不存在。
    """
    try:
        return _docker(["image", "inspect", image], timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
