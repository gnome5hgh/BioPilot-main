# biopilot/engine/intent/data —— 意图知识库（随包发布）

本目录是意图模块的**代码资产**，不是运行期数据：它与类别枚举做 fail-closed 校验，
必须与代码同版本演进，因此跟着 wheel 发布，不随运行数据根重定向。

| 文件 | 说明 |
|---|---|
| `taxonomy.yaml` | 类别知识库：11 个类别 × {判定口径, 示例句}。口径与示例一起构成判定模型的 criteria——**口径要写清「是什么 / 不包什么」**，类别之间的边界才是判定的全部难点 |
| `rules.yaml` | 规则层的高精度模式：每条 = {目标类别, 正则, 为什么这条算高精度}。命中即定类、不命中即放行 |

两份资产由 `biopilot/engine/intent/rules/taxonomy.py` 的 `load_taxonomy` 装载并做 **fail-closed** 校验：类别缺条目、出现未知类别、缺描述、缺示例、规则指向未知类别、模式非法正则、模式与示例逐字重复——都在启动期报错并**点名具体类别**。类别集合必须与 `IntentType` 枚举（11 值）逐项一致。

领域意图与领域 agent 一一对应：`paper` / `note` / `research` / `bioinformatics` / `index` 分别对应 paper-agent / note-agent / research-agent / bio-agent / rag-agent。这张对应关系是责任归属，不是运行时路由——派发仍由 supervisor 自主决定。

## 改动这两份资产

直接改文件即可，没有需要重跑的标定流程：类别与规则都是声明式的，装载期校验会挡住写错的情况。

加规则前先做一次自检：**有没有一句正常的话会被它误吸？** 举不出反例才加——规则层命中即短路，误命中没有下游兜底。`tests/intent/test_taxonomy_kb.py` 里有一组**明确不该命中**的输入，新规则应当先拿它过一遍。

改完跑：

```bash
conda run -n biopilot python -m pytest tests/intent -q
```

## 题集（评测集）不在这里

标定题集按实验归属放在 `scripts/intent/calibration/goldens/{source,audited}/`——**实验资产、`scripts/` 不入库**，所以本机那份是唯一副本，清理脚本目录时不要连它一起删。类别换代后旧题集需要重标（新类别在旧 18 类里可能没有对应项），不要拿旧标签直接跑新类别。
