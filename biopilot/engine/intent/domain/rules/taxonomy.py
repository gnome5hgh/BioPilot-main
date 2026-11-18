# biopilot/engine/intent/domain/rules/taxonomy.py
"""意图知识库的装载与校验：类别（描述 + 示例句）与规则层的高精度模式。

判定要回答的是「用户要哪一类工作」，而类别之间的边界正是这件事的全部难点，
所以知识库的完整性必须**装载期 fail-closed**：类别缺条目、缺描述、规则指向
未知类别，都在启动时明确报错并**指出是哪个类别**——不许跑到某一轮才静默走偏。

两份资产都随包发布（`engine/intent/domain/data/`）：`taxonomy.yaml` 写各类的判定口径与
示例句（判定模型看到的 criteria），`rules.yaml` 写规则层的高精度模式。类别词汇由
`engine/intent/constants/` 声明（`INTENT_CLASSES` 从枚举派生），装载时与知识库逐项对齐。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from biopilot.engine.intent.constants import INTENT_CLASSES
from biopilot.engine.intent.domain.schemas import IntentClass, Rule


class TaxonomyError(ValueError):
    """知识库装载校验失败。fail-closed：宁可启动就报错，不要运行期静默走偏。"""


@dataclass(frozen=True)
class Taxonomy:
    """装载好的知识库：类别表 + 规则表。

    Attributes:
        classes: dict[str, IntentClass]，类别名 → 类别定义
        rules: tuple[Rule, ...]，按声明顺序（命中即返回第一条）
    """

    classes: dict[str, IntentClass]
    rules: tuple[Rule, ...]

    def criteria(self) -> dict[str, str]:
        """判定模型的选项表：类别 → 「判定口径 + 示例句」。

        Returns:
            dict[str, str]：键为类别名，值为该类的描述与示例句拼成的文本。
        """
        return {name: f"{cls.description}\n示例：" + "；".join(cls.examples)
                for name, cls in self.classes.items()}

    def match(self, text: str) -> str | None:
        """规则层判定：按声明顺序取第一条命中的模式。

        规则层**只做高精度触发**，不命中即放行给下一层——它永不猜测，因此这里
        没有分值、没有阈值，命中与不命中是两件事而不是同一件事的两端。

        Args:
            text: str，用户输入原文。

        Returns:
            命中的类别名；没有任何模式命中时返回 None。
        """
        t = (text or "").strip()
        if not t:
            return None
        for rule in self.rules:
            if rule.pattern.search(t):
                return rule.intent
        return None


def _parse_classes(raw: dict) -> dict[str, IntentClass]:
    """校验并构造类别表（类别集合必须与 INTENT_CLASSES 逐项相等）。

    Args:
        raw: dict，taxonomy.yaml 的顶层映射。

    Returns:
        dict[str, IntentClass]：类别名 → 类别定义。

    Raises:
        TaxonomyError: 缺条目、未知类别、缺描述、或缺示例句。报错点名具体类别。
    """
    declared = raw.get("classes")
    if not isinstance(declared, dict) or not declared:
        raise TaxonomyError("taxonomy.yaml 缺 classes 段（或为空）")

    missing = [n for n in INTENT_CLASSES if n not in declared]
    if missing:
        raise TaxonomyError(f"知识库缺类别条目：{'、'.join(missing)}（枚举里有、知识库里没有）")
    unknown = [n for n in declared if n not in INTENT_CLASSES]
    if unknown:
        raise TaxonomyError(f"知识库出现未知类别：{'、'.join(sorted(unknown))}")

    classes: dict[str, IntentClass] = {}
    for name in INTENT_CLASSES:
        entry = declared[name]
        if not isinstance(entry, dict):
            raise TaxonomyError(f"类别 {name} 的定义必须是映射（含 description 与 examples）")
        description = entry.get("description")
        if not (isinstance(description, str) and description.strip()):
            raise TaxonomyError(f"类别 {name} 缺描述")
        examples = entry.get("examples")
        if not (isinstance(examples, list) and examples):
            raise TaxonomyError(f"类别 {name} 缺示例句")
        cleaned = tuple(str(e).strip() for e in examples if str(e).strip())
        if not cleaned:
            raise TaxonomyError(f"类别 {name} 的示例句全为空")
        classes[name] = IntentClass(name=name, description=description.strip(), examples=cleaned)
    return classes


def _parse_rules(raw: dict, classes: dict[str, IntentClass]) -> tuple[Rule, ...]:
    """校验并编译规则表。

    Args:
        raw: dict，rules.yaml 的顶层映射。
        classes: dict[str, IntentClass]，已校验的类别表（用于校验规则指向）。

    Returns:
        tuple[Rule, ...]：按声明顺序编译好的规则。

    Raises:
        TaxonomyError: 规则缺 intent/pattern、指向未知类别、正则不合法，
            或某条规则的模式原文与某条示例句逐字相同（同一句话不该两头都占）。
    """
    items = raw.get("rules")
    if not isinstance(items, list) or not items:
        raise TaxonomyError("rules.yaml 缺 rules 段（或为空）")

    all_examples = {e for cls in classes.values() for e in cls.examples}
    rules: list[Rule] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise TaxonomyError(f"第 {i + 1} 条规则必须是映射（含 intent 与 pattern）")
        intent = item.get("intent")
        if intent not in classes:
            raise TaxonomyError(f"第 {i + 1} 条规则指向未知类别：{intent!r}")
        raw_pattern = item.get("pattern")
        if not (isinstance(raw_pattern, str) and raw_pattern.strip()):
            raise TaxonomyError(f"规则（intent={intent}）缺 pattern")
        try:
            compiled = re.compile(raw_pattern)
        except re.error as exc:
            raise TaxonomyError(
                f"规则（intent={intent}）的 pattern 不是合法正则：{raw_pattern!r}（{exc}）") from exc
        if raw_pattern in all_examples:
            raise TaxonomyError(
                f"规则（intent={intent}）的 pattern 与某条示例句逐字相同：{raw_pattern!r}"
                "——同一句话不该既当示例又当规则")
        rules.append(Rule(intent=intent, pattern=compiled,
                          raw=raw_pattern, note=str(item.get("note", ""))))
    return tuple(rules)


def taxonomy_from_raw(raw_classes: dict, raw_rules: dict) -> Taxonomy:
    """从已装载的知识库映射构造并校验 Taxonomy（fail-closed，纯函数无 I/O）。

    Args:
        raw_classes: dict，taxonomy.yaml 的顶层映射。
        raw_rules: dict，rules.yaml 的顶层映射。

    Returns:
        Taxonomy：校验通过的类别表与规则表。

    Raises:
        TaxonomyError: 任一份资产缺条目、指向未知类别或校验不过（报错点名具体类别）。
    """
    classes = _parse_classes(raw_classes)
    rules = _parse_rules(raw_rules, classes)
    return Taxonomy(classes=classes, rules=rules)
