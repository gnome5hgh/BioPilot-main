"""RunShellTool：在一次性容器的沙箱里跑一段 shell 命令或脚本。

与 run_python 共用同一套容器政策与执行尾部（``sandboxed.py``），差别只有解释器
入口：命令文本写进 ``/work/_run.sh`` 后由 bash 执行。命令参数声明为
``format="shell_command"``，因此命令防护中间件会在执行前接管它的文本（熔断毁灭性
指令、对其余不在常用清单内的命令登记升级因）——但那是策略轴，真正的边界仍是容器。

风险档位与 run_python 一致取中档：安全来自墙而非档位，命令层面的额外确认由
命令防护按命令内容决定，而不是每次调用都弹框。
"""
from biopilot.engine.security.services import sandbox as sb
from biopilot.engine.tool import ToolResult
from biopilot.tools.code.sandboxed import SandboxedTool


class RunShellTool(SandboxedTool):
    """在隔离容器里执行 shell 命令或脚本的工具。

    Attributes:
        name: str，工具名 "run_shell"
        description: str，工具描述（隔离语义、可用工具、非交互与产物去向）
        parameters: dict，JSON Schema（command，format=shell_command）
        risk_level: str，"medium"（安全来自沙箱而非档位）
        side_effects: list[str]，["read_file", "write_file"]
    """

    name = "run_shell"
    scratch_kind = "shell"
    subject = "命令"
    description = (
        "在隔离沙箱里执行一段 shell 命令或脚本（管道、循环、多行脚本都可以）。"
        "隔离方式：一次性容器，**默认无网络**；只有 /work 可写，对话附件的数据"
        "文件只读挂在 /corpus/uploads 下。"
        "容器内预装 bash 与常用 coreutils（ls/cat/grep/sed/awk/find/tar 等），"
        "没有 curl/wget/git 与生信命令行工具（samtools、Rscript 等）。"
        "**不要跑交互式命令**（vim/top/less/ssh）：没有 TTY，stdin 已关闭，它们"
        "会一直等到超时。"
        "命令写到 /work 下即可产出文件，产出会自动登记到文件管理。"
        "数值分析、统计与画图请优先用 run_python（预装 pandas/numpy/matplotlib "
        "等库）；本工具适合目录查看、文本处理与管道组合。"
        "毁灭性命令会被直接拒绝；不在常用只读清单内的命令执行前会请用户确认。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "format": "shell_command",
                "description": "要执行的 shell 命令或脚本（可多行；输出用 echo/printf 打印）",
            },
        },
        "required": ["command"],
    }
    risk_level = "medium"                     # 安全来自沙箱而非档位：默认免问档内静默
    side_effects = ["read_file", "write_file"]

    def _sandbox_call(self, command: str,
                      policy: sb.SandboxPolicy) -> sb.SandboxResult:
        """用 bash 入口执行命令文本。"""
        return sb.run_shell(command, policy)

    def execute(self, command: str) -> ToolResult:
        """在沙箱里执行命令并返回结果。

        Args:
            command: str，要执行的 shell 命令或脚本（可多行）

        Returns:
            ToolResult；命令为空、沙箱不可用或未装配配置时返回错误文本（不抛异常）。
        """
        if not command or not command.strip():
            return ToolResult(text="命令为空，未执行", is_error=True)
        return self._execute(command)
