"""意图模块的常量：类别词汇与知识库资产路径。

只有跨**文件**共享、且不属于某个消费方的常量才放这里——类别名与知识库位置符合
这条；结构常量与算法契约（正则、重试退避基数、提示词文案）留在各自的消费处就地
声明。类别**不分组**：曾经那张「意图 → 业务/系统」的映射只服务已删的派发过滤，
没有运行时消费者；每个类别该派给谁由 `rules_block` 的文案与 supervisor 的判断承担。

知识库是**随包发布的代码资产**（`engine/intent/data/`），不是运行期数据：它与
`IntentType` 做 fail-closed 校验，必须与枚举同版本演进，因此跟着 wheel 走，不随
运行数据根重定向。
"""
from pathlib import Path

from .enums import IntentType

__all__ = ["INTENT_CLASSES", "INTENT_KB_DIR", "RULES_PATH", "TAXONOMY_PATH"]

#: 类别词汇：**由枚举派生**（枚举是唯一声明点，知识库必须与它逐项一致，装载期校验）。
#: 顺序即枚举声明顺序；规则表按自己的声明顺序匹配，与本元组无关。
INTENT_CLASSES: tuple[str, ...] = tuple(t.value for t in IntentType)

#: 知识库目录（本文件位于 engine/intent/constants/，向上一级即 intent/ 包根）。
INTENT_KB_DIR = Path(__file__).resolve().parents[1] / "data"

#: 类别知识库与规则表的默认路径（单测与生产共用；显式传参可指向替身文件）
TAXONOMY_PATH = INTENT_KB_DIR / "taxonomy.yaml"
RULES_PATH = INTENT_KB_DIR / "rules.yaml"
