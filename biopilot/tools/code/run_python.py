"""RunPythonTool：在一次性容器的沙箱里跑一段 Python 代码。

工具本身不做隔离——墙由 ``core/security/services/sandbox.py`` 砌（断网、论文库
只读、一个临时目录可写）。本工具负责：按配置组装政策、起容器、把结果整理成模型
能读的固定列文本，并把安全相关的事实（容器政策快照、退出码、超时、产物清单）
经结构化摘要通道交给审计。

风险档位声明为中档（默认免问档内静默）：它的安全来自墙、不来自档位——把「沙箱已
兜底」编码进档位是混淆两条轴。环境不可用时返回可行动的错误文本（fail-closed），
绝不退回进程内执行。
"""
import uuid
from pathlib import Path

from biopilot.core.security.services import sandbox as sb
from biopilot.core.tool import Tool, ToolResult
from biopilot.tools.common.factory import semantic_roots

#: 容器内论文库的挂载点——只读挂载的固定去处，脚本据此定位 PDF。
_CORPUS_MOUNT = "/corpus"

#: 单段输出的字符上限——脚本可能打印整张表刷爆上下文；截断并标注，不静默吞掉。
_OUTPUT_CAP = 16000


def _clip(text: str) -> str:
    """把过长输出截断到上限并标注，避免一次执行灌爆模型上下文。"""
    if len(text) <= _OUTPUT_CAP:
        return text
    return text[:_OUTPUT_CAP] + f"\n…（输出过长，已截断，共 {len(text)} 字符）"


class RunPythonTool(Tool):
    """在隔离容器里执行 Python 代码的工具。

    Attributes:
        name: str，工具名 "run_python"
        description: str，工具描述（含沙箱语义：断网 / 论文库只读 / 产物在临时目录）
        parameters: dict，JSON Schema（code）
        risk_level: str，"medium"（默认免问档内；安全来自沙箱而非档位）
        side_effects: list[str]，["read_file", "write_file"]
        _config: BioPilotConfig，装配注入（组装沙箱政策用）
    """

    name = "run_python"
    description = (
        "在隔离沙箱里运行一段 Python 代码并把结果取回来（分析论文数据、算统计、画图）。"
        "隔离方式：一次性容器，**无网络**，论文库只读挂在 /corpus/pdf 下，"
        "只有 /work 可写。如需读取 PDF，请用 /corpus/pdf 下的路径。"
        "代码写到 /work 下即可产出文件——产出清单会随结果返回，"
        "需要长期留存时再用 write_file 写到目标目录（那一步会另行确认）。"
        "依赖库已预装：pandas、numpy、matplotlib、pypdf、scipy。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的完整 Python 源码（可多行；结果用 print 输出）",
            },
        },
        "required": ["code"],
    }
    risk_level = "medium"                     # 安全来自沙箱而非档位：默认免问档内静默
    side_effects = ["read_file", "write_file"]

    def _build_policy(self, cfg) -> sb.SandboxPolicy:
        """按配置组装本次执行政策：临时目录、只读挂载、资源上限。

        论文库（pdf 根）默认只读挂载到容器内 ``/corpus/pdf``；``sandbox.read_roots``
        里点名的语义根再各挂一份到 ``/corpus/<根名>``。每次都新建一个独立的
        临时目录，使产物清单只反映本次执行。

        Args:
            cfg: PaperFlowConfig，配置来源

        Returns:
            SandboxPolicy，可直接交给沙箱能力。
        """
        roots = semantic_roots(cfg)
        scratch = Path(roots["scratch"]) / "code" / f"run-{uuid.uuid4().hex[:8]}"

        mounts: list[tuple[str, str]] = []
        if cfg.corpus.pdf_dir:
            mounts.append((str(Path(cfg.corpus.pdf_dir).resolve()), f"{_CORPUS_MOUNT}/pdf"))
        for name in cfg.security.sandbox.read_roots:
            path = roots.get(name)
            if path:
                mounts.append((str(Path(path).resolve()), f"{_CORPUS_MOUNT}/{name}"))

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

    @staticmethod
    def _policy_summary(policy: sb.SandboxPolicy) -> dict:
        """容器政策快照——落进审计，回答「这次代码在什么墙里跑的」。"""
        return {
            "image": policy.image,
            "network": policy.network,
            "read_mounts": [f"{h}:{c}:ro" for h, c in policy.read_mounts],
            "memory": policy.memory,
            "cpus": policy.cpus,
            "pids_limit": policy.pids_limit,
            "timeout_s": policy.timeout_s,
        }

    @staticmethod
    def _format(res: sb.SandboxResult, scratch: str) -> str:
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
        if res.files:
            lines += [f"{Path(scratch) / f['name']} ({f['size']} B)" for f in res.files]
        else:
            lines.append("(无)")
        lines += [
            "--- 说明 ---",
            "本次在隔离容器中执行：无网络；论文库只读。产出文件在临时目录里，"
            "如需留存请用 write_file 写到目标目录。",
        ]
        return "\n".join(lines)

    def execute(self, code: str) -> ToolResult:
        """在沙箱里执行代码并返回结果。

        Args:
            code: str，要执行的 Python 源码

        Returns:
            ToolResult；沙箱不可用或未装配配置时返回错误文本（不抛异常）。
        """
        cfg = getattr(self, "_config", None)
        if cfg is None:
            return ToolResult(text="run_python 未装配配置，无法执行")
        if not cfg.security.sandbox.enabled:
            return ToolResult(text="沙箱代码执行已在配置中关闭（sandbox.enabled=false）")

        policy = self._build_policy(cfg)
        try:
            res = sb.run_python(code, policy)
        except sb.SandboxUnavailable as e:
            return ToolResult(text=f"沙箱不可用，代码未执行：{e}")

        summary = {
            "exit_code": res.exit_code,
            "timed_out": res.timed_out,
            "duration_ms": res.duration_ms,
            "files": [
                {"name": f["name"], "path": str(Path(policy.scratch) / f["name"]),
                 "size": f["size"]}
                for f in res.files
            ],
            "sandbox": self._policy_summary(policy),
        }
        return ToolResult(text=self._format(res, policy.scratch), summary=summary)
