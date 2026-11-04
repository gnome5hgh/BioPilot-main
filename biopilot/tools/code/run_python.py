"""RunPythonTool：在一次性容器的沙箱里跑一段 Python 代码。

工具本身不做隔离——墙由 ``core/security/services/sandbox.py`` 砌（断网、论文库
只读、一个临时目录可写）。本工具负责声明参数与风险档位，其余执行尾部在
``sandboxed.py`` 里与 run_shell 共用。

风险档位声明为中档（默认免问档内静默）：它的安全来自墙、不来自档位——把「沙箱已
兜底」编码进档位是混淆两条轴。环境不可用时返回可行动的错误文本（fail-closed），
绝不退回进程内执行。
"""
from biopilot.core.security.services import sandbox as sb
from biopilot.core.tool import ToolResult
from biopilot.tools.code.sandboxed import SandboxedTool


class RunPythonTool(SandboxedTool):
    """在隔离容器里执行 Python 代码的工具。

    Attributes:
        name: str，工具名 "run_python"
        description: str，工具描述（含沙箱语义：断网 / 只读挂载 / 只有 /work 可写）
        parameters: dict，JSON Schema（code）
        risk_level: str，"medium"（默认免问档内；安全来自沙箱而非档位）
        side_effects: list[str]，["read_file", "write_file"]
    """

    name = "run_python"
    scratch_kind = "code"
    subject = "代码"
    description = (
        "在隔离沙箱里运行一段 Python 代码并把结果取回来（分析数据、算统计、画图）。"
        "隔离方式：一次性容器，**无网络**；对话附件的数据文件只读挂在 "
        "/corpus/uploads 下（csv/xlsx/h5ad 等），只有 /work 可写。"
        "论文 PDF 不挂进沙箱——需要读全文时用 read_pdf 工具，或在代码里分析"
        "对话附件里的数据文件。"
        "代码写到 /work 下即可产出文件，产出会自动登记到文件管理。"
        "依赖库已预装：pandas、numpy、scipy、statsmodels、matplotlib、seaborn、"
        "scikit-learn、scanpy、anndata、biopython、lifelines、openpyxl、pypdf。"
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

    def _sandbox_call(self, code: str, policy: sb.SandboxPolicy) -> sb.SandboxResult:
        """用 Python 解释器入口执行源码。"""
        return sb.run_python(code, policy)

    def execute(self, code: str) -> ToolResult:
        """在沙箱里执行代码并返回结果。

        Args:
            code: str，要执行的 Python 源码

        Returns:
            ToolResult；沙箱不可用或未装配配置时返回错误文本（不抛异常）。
        """
        return self._execute(code)
