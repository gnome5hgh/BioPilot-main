"""Tool 安全元数据的加载期校验，以及资源引用参数的运行期形状校验。

AgentRegistry 与 SkillRegistry 共用加载期校验；``validate_ref_args`` 在每次工具
执行前校验 ``file_id``/``doc_id``/``file_name`` 等参数，防止畸形引用进入内部
HTTP 路径或数据库查询。
"""
import re
from typing import TYPE_CHECKING

from biopilot.core.constants import PROVENANCE_KINDS, RISK_LEVELS, SIDE_EFFECTS

_ID_FORMATS = {"file_id", "doc_id", "paper_id"}
_NAME_FORMATS = {"file_name", "document_name"}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f]")


def validate_ref_args(tool: "Tool", args: dict) -> list[dict]:
    """校验工具参数里的资源引用形状。

    Args:
        tool: 工具实例（读 ``parameters`` 里的 ``format``）。
        args: 已解析的参数。

    Returns:
        list[dict]：违规项 ``{param, value, reason}``；空列表表示通过。
    """
    props = (getattr(tool, "parameters", None) or {}).get("properties") or {}
    violations: list[dict] = []
    for name, schema in props.items():
        value = (args or {}).get(name)
        if not isinstance(value, str):
            continue
        fmt = (schema or {}).get("format")
        if fmt in _ID_FORMATS and not _ID_RE.fullmatch(value):
            violations.append({
                "param": name,
                "value": value,
                "reason": "id 只能包含字母、数字、下划线和短横线，长度 1-64",
            })
        elif fmt in _NAME_FORMATS:
            text = value.strip()
            if (not text or len(text) > 255 or "/" in text or "\\" in text
                    or ".." in text or _CONTROL_RE.search(text)):
                violations.append({
                    "param": name,
                    "value": value,
                    "reason": "文件名不能为空、不能含路径分隔符/.. /控制字符，长度不超过 255",
                })
    return violations

if TYPE_CHECKING:
    from biopilot.core.tool.domain.entity.tool import Tool


def validate_tool(tool: "Tool") -> None:
    """校验 Tool 的安全元数据字段，非法值立即抛 ValueError（加载时前置防线）。

    AgentRegistry 与 SkillRegistry 共用：不安全配置不进系统。
    校验点：risk_level ∈ RISK_LEVELS；side_effects 每个值 ∈ SIDE_EFFECTS；
    provenance 为 None 或 ∈ PROVENANCE_KINDS。

    Args:
        tool: 待校验的 Tool 实例

    Raises:
        ValueError: 任一字段非法，携带工具名与合法值列表

    """
    if tool.risk_level not in RISK_LEVELS:
        raise ValueError(
            f"Tool '{tool.name}': 非法 risk_level '{tool.risk_level}'，"
            f"合法值: {sorted(RISK_LEVELS)}"
        )
    invalid_effects = [s for s in tool.side_effects if s not in SIDE_EFFECTS]
    if invalid_effects:
        raise ValueError(
            f"Tool '{tool.name}': 非法 side_effects: {invalid_effects}，"
            f"合法值: {sorted(SIDE_EFFECTS)}"
        )
    if tool.provenance is not None and tool.provenance not in PROVENANCE_KINDS:
        raise ValueError(
            f"Tool '{tool.name}': 非法 provenance '{tool.provenance}'，"
            f"合法值: None / {sorted(PROVENANCE_KINDS)}"
        )
