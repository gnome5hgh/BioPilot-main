"""review-agent 的工具装配：两类审查的共用工具并集。

两类审查各是一份 skill(review-note / review-plan),开审前按任务加载：
- review-note：笔记审查(结构/保真/一致/完整四维 + submit_review 交裁决)
- review-plan：研究选题产物审查(四产物交叉核验 + 素材熔断诚实性, submit_review 交裁决)
两份流程共用同一工具并集。
"""
from biopilot.config import BioPilotConfig
from biopilot.cli.services.tool_assembly import make_tools
from biopilot.tools import (
    ReadFileTool, ReadPdfTool, FormatCheckTool, SubmitReviewTool, GlobTool, GrepTool,
)
from biopilot.tools.orchestration.spawn import SpawnSubAgentTool
from biopilot.tools.recall import get_recall_tools

TOOLS = make_tools(BioPilotConfig.from_env(), [
    ReadFileTool, ReadPdfTool, FormatCheckTool, SubmitReviewTool, GlobTool, GrepTool,
    SpawnSubAgentTool(agent_timeouts=BioPilotConfig.from_env().agents.timeouts,
                   max_turns=BioPilotConfig.from_env().agents.max_turns),
]) + get_recall_tools()
