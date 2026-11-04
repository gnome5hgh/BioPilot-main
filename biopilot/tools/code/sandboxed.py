"""沙箱执行工具的共用部分：政策组装、产物登记与结果渲染。

run_python 与 run_shell 的差别只有参数 schema、容器内执行入口与说明文案；
政策怎么组装、产物怎么登记、结果怎么落成文本必须完全一致——否则两条执行路径
会各自演化出不同的墙。共用逻辑集中在这里，子类只实现 `_sandbox_call`。

工具本身不做隔离——墙由 ``engine/security/services/sandbox.py`` 砌（断网、根只读、
只读挂载、一个临时目录可写）。环境不可用时返回可行动的错误文本（fail-closed），
绝不退回进程内执行。
"""
import logging
import mimetypes
import re
import shutil
import uuid
from pathlib import Path

from biopilot.config import user_cache_root
from biopilot.engine.security.services import sandbox as sb
from biopilot.engine.tool import Tool, ToolResult
from biopilot.engine.tool.services.roots import semantic_roots

logger = logging.getLogger(__name__)

#: 容器内语料挂载的固定前缀——只读挂载的语义根各占一个子目录。
_CORPUS_MOUNT = "/corpus"

#: 单段输出的字符上限——脚本可能打印整张表刷爆上下文；截断并标注，不静默吞掉。
_OUTPUT_CAP = 16000


def _safe(value: str) -> str:
    """把用户/会话 id 收敛成可安全拼进本地临时路径的片段。"""
    text = re.sub(r"[^A-Za-z0-9._-]", "_", str(value or "")).replace("..", "_")
    return text or "unknown"


def _clip(text: str) -> str:
    """把过长输出截断到上限并标注，避免一次执行灌爆模型上下文。"""
    if len(text) <= _OUTPUT_CAP:
        return text
    return text[:_OUTPUT_CAP] + f"\n…（输出过长，已截断，共 {len(text)} 字符）"


class SandboxedTool(Tool):
    """沙箱执行工具的共用执行尾部。

    Attributes:
        scratch_kind: str，scratch 子目录名（code / shell），不同执行类型各用各的目录
        subject: str，说明文案里的执行对象（代码 / 命令）
    """

    scratch_kind = "code"
    subject = "代码"

    def _build_policy(self, cfg, user_id: str | None = None,
                      conversation_id: str | None = None) -> sb.SandboxPolicy:
        """按配置组装本次执行政策：临时目录、只读挂载、资源上限。

        ``sandbox.read_roots`` 里点名的语义根各挂一份到 ``/corpus/<根名>``；
        对话附件只读挂到 ``/corpus/uploads``。每次执行新建一个独立的临时目录，
        使产物清单只反映本次执行。

        Args:
            cfg: BioPilotConfig，配置来源
            user_id: 归属用户（有值时挂载该用户的上传附件目录）
            conversation_id: 会话 id（定位附件目录）

        Returns:
            SandboxPolicy，可直接交给沙箱能力。
        """
        roots = semantic_roots(cfg)
        scratch = (Path(roots["scratch"]) / self.scratch_kind
                   / f"run-{uuid.uuid4().hex[:8]}")

        mounts: list[tuple[str, str]] = []
        for name in cfg.security.sandbox.read_roots:
            path = roots.get(name)
            if path:
                mounts.append((str(Path(path).resolve()), f"{_CORPUS_MOUNT}/{name}"))
        # 对话附件：只读挂进 /corpus/uploads——模型写的脚本据此读数据文件
        if user_id and conversation_id:
            uploads = (user_cache_root(cfg) / _safe(user_id) / "uploads"
                       / _safe(conversation_id))
            if uploads.is_dir():
                mounts.append((str(uploads.resolve()), f"{_CORPUS_MOUNT}/uploads"))

        s = cfg.security.sandbox
        return sb.SandboxPolicy(
            image=s.image,
            scratch=str(scratch),
            read_mounts=tuple(mounts),
            network=s.network,
            memory=s.memory,
            cpus=s.cpus,
            pids_limit=s.pids_limit,
            timeout_s=s.timeout_s,
        )

    def _persist_artifacts(self, files: list[dict]) -> None:
        """把本次执行的产物登记进平台文件管理（OSS + `bio_file`）。

        scratch 挂载在宿主、容器即弃——不登记的话产物随临时目录清理丢失，网页也
        看不到。对象键与元数据行都由 Java 写；单文件失败只记日志，不影响其余
        产物与工具返回（本地路径仍在 summary 里）。

        Args:
            files: summary["files"] 列表（就地补 oss_key）。
        """
        from biopilot.engine.tool.services.runtime_context import get_memory_context
        ctx = get_memory_context()
        user_id = getattr(ctx, "user_id", None) if ctx is not None else None
        if not user_id or not files:
            return
        try:
            from biopilot.common.platform import make_platform_client
            cfg = getattr(self, "_config", None)
            if cfg is None:
                from biopilot.config import BioPilotConfig
                cfg = BioPilotConfig.from_env()
            platform = make_platform_client(cfg)
        except Exception as e:
            logger.warning("分析产物持久化失败（不阻断工具返回）：%r", e)
            return
        try:
            run_id = Path(files[0]["path"]).parent.name
            for f in files:
                src = Path(f["path"])
                if not src.exists() or not src.is_file():
                    continue
                try:
                    name = str(f.get("name") or src.name)
                    content_type = (mimetypes.guess_type(name)[0]
                                    or "application/octet-stream")
                    created = platform.upload_artifact(
                        str(user_id), run_id, name, src.read_bytes(), content_type)
                    f["oss_key"] = created.get("oss_key", "")
                    f["file_id"] = created.get("file_id", "")
                except Exception as exc:
                    logger.warning("分析产物上传失败（%s）：%r", f.get("name"), exc)
        finally:
            platform.close()

    @staticmethod
    def _policy_summary(policy: sb.SandboxPolicy) -> dict:
        """容器政策快照——落进审计，回答「这次执行在什么墙里跑的」。"""
        return {
            "image": policy.image,
            "network": policy.network,
            "read_mounts": [f"{h}:{c}:ro" for h, c in policy.read_mounts],
            "memory": policy.memory,
            "cpus": policy.cpus,
            "pids_limit": policy.pids_limit,
            "timeout_s": policy.timeout_s,
        }

    def _format(self, res: sb.SandboxResult, policy: sb.SandboxPolicy,
                files: list[dict] | None = None) -> str:
        """把结果整理成固定列文本：退出码 / stdout / stderr / 产出文件 / 说明。"""
        head = f"退出码: {res.exit_code}（耗时 {res.duration_ms}ms）"
        if res.timed_out:
            head += "，已超时终止"
        lines = [
            head,
            "--- stdout ---",
            _clip(res.stdout.rstrip("\n")) or "(空)",
            "--- stderr ---",
            _clip(res.stderr.rstrip("\n")) or "(空)",
            "--- 产出文件 ---",
        ]
        shown = files if files is not None else res.files
        if shown:
            for f in shown:
                line = f"{f['name']} ({f['size']} B)"
                if f.get("file_id"):
                    line += f"（已登记到文件管理，file_id={f['file_id']}）"
                lines.append(line)
        else:
            lines.append("(无)")
        network = "允许联网（由沙箱配置开启）" if policy.network else "无网络"
        lines += [
            "--- 说明 ---",
            f"本次在隔离容器中执行：{network}，只有 /work 可写。"
            "产出文件已自动登记到文件管理（登记失败时仍保留在临时目录）。",
        ]
        return "\n".join(lines)

    def _sandbox_call(self, source: str, policy: sb.SandboxPolicy) -> sb.SandboxResult:
        """在沙箱里执行源码——由子类选择解释器入口。"""
        raise NotImplementedError

    def _execute(self, source: str) -> ToolResult:
        """按统一尾部执行：配置检查 → 起沙箱 → 登记产物 → 渲染结果 → 清临时目录。"""
        cfg = getattr(self, "_config", None)
        if cfg is None:
            return ToolResult(text=f"{self.name} 未装配配置，无法执行")
        if not cfg.security.sandbox.enabled:
            return ToolResult(text="沙箱执行已在配置中关闭（sandbox.enabled=false）")

        from biopilot.engine.tool.services.runtime_context import get_memory_context
        ctx = get_memory_context()
        policy = self._build_policy(
            cfg,
            user_id=getattr(ctx, "user_id", None) if ctx is not None else None,
            conversation_id=getattr(ctx, "agent_id", None) if ctx is not None else None)
        try:
            res = self._sandbox_call(source, policy)
        except sb.SandboxUnavailable as e:
            return ToolResult(text=f"沙箱不可用，{self.subject}未执行：{e}")

        files = [
            {"name": f["name"], "path": str(Path(policy.scratch) / f["name"]),
             "size": f["size"]}
            for f in res.files
        ]
        # 产物登记是落盘之后的收尾：失败只在 _persist_artifacts 内记日志，
        # 不影响本次执行结果返回（本地路径仍可用）。
        self._persist_artifacts(files)
        summary = {
            "exit_code": res.exit_code,
            "timed_out": res.timed_out,
            "duration_ms": res.duration_ms,
            "files": files,
            "sandbox": self._policy_summary(policy),
        }
        try:
            text = self._format(res, policy, files)
        finally:
            # 产物已上传平台；scratch 是执行期临时目录，用完即删。
            shutil.rmtree(policy.scratch, ignore_errors=True)
        return ToolResult(text=text, summary=summary)
