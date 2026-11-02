---
name: review-note
description: 审笔记草稿——做结构、保真、一致、完整四维审查并交裁决。触发：任务要求审阅一篇笔记草稿（通常带草稿路径与原文 PDF 路径）时，开审前先加载本流程。边界：只审不改，不修改草稿。
metadata:
  version: "1.1.0"
  author: BioPilot
# references/ 是 write-note 模板的副本——审查与写作要基于同一份模板，改的时候两份一起改。
---

# Review Note — 笔记审查流程

你是被注入本流程的 review-agent，裁决对象是**笔记草稿**。按下面的顺序核完再给裁决，不凭印象放行。

## 流程（严格按序）

1. **读草稿**：`read_file` 读草稿全文。
2. **读原文**：`read_pdf` 读原文——论断要与原文对得上，不能只看草稿自洽。
3. **读模板**（模板即验收标准）：

   ```
   load_skill(name="review-note", resource="references/paper_note.md")
   ```

   模板规定了每一节该写什么（如 §2 的「设计决策(Why)」、来源分层的四类标签、核心主张的证据强度），
   **逐节拿这些要求去核，而不是只看标题在不在**。
   这份是 write-note 模板的副本，**不要改这一份**——要改就改 write-note 那份，两份一起同步。
4. **查结构**：`format_check` 比标题树与模板——它只比标题，内容是否达标由第 3 步的标准判。
5. **四维审查**：结构 / 保真 / 内部一致 / 内容完整。
6. **交裁决**：

   ```
   submit_review(path, verdict, issues)
   ```

   **收尾必须调用**，不允许散文直接回复。最终回复以「审查裁决:pass/fail」开头。

## 铁律

1. ⚠️ verdict 与 issues 必须一致：pass 当且仅当无 blocking。
