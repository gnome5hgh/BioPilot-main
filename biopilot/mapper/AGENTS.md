# mapper

## Scope

- 覆盖 `biopilot/mapper/`：引擎领域表与跨栈只读表的全部 SQL。
- 引擎表的 DDL 唯一落点是 [`../engine/memory/storage/database.py`](../engine/memory/storage/database.py) 的 `_SCHEMA`；本层只写查询，不建表。唯一例外是改名类迁移（如列 RENAME 无法经 _ADDITIVE_COLUMNS 表达），走 `server/script/sql/migrations/` 一次性脚本，完成后与 `_SCHEMA` 一致。

## Module Positioning

- 角色：`capability-or-domain-leaf-manifest-dir`
- 职责：SQL 的唯一存放点——service 层不写裸 SQL，所有引擎领域数据的读写都经本层函数。

## Directory Structure

- `base.py` — `shared_db()` 懒建单例（轻量 SQL 共用连接）
- `message_mapper.py` / `agent_state_mapper.py` / `user_mapper.py` — 会话消息/agent 状态/删户清理
- `rag_index_mapper.py` — `bio_rag_index_state` 删户清理
- `rag_paper_status_mapper.py` — 论文索引状态唯一落点的读写（含与 `bio_file` 勾选真相的 JOIN 守卫）

## Core Logic

- **函数式形状**：模块级函数、`db` 首参、SQL 字符串字面量 + `?` 占位符元组（`MemoryDB` 统一转 `%s`；SQL 字面量不得出现 `?` 以外的占位写法）。
- **读—改—写必须包事务**：多语句的写路径用 `db.transaction()` 包住（嵌套安全）；单条写可裸执行。
- **跨栈 JOIN 守卫**：与平台表（`bio_file`）关联的条件（如 `kb_enabled=1`）写进 JOIN 片段而不是后置 WHERE——守卫与取数同语句才不被并发打穿。
- 写失败的语义由调用方定：状态类写失败只告警降级，不炸主流程。

## Usage And Change Notes

- 新增 mapper：一个关注点一个文件，函数带完整 docstring（作用/Args/Returns）；给已有表加列要同步 `_SCHEMA` 并登记 `_ADDITIVE_COLUMNS`。
- 平台表（`bio_file`/`bio_schedule_task` 等）**只读**；写者是 Java（单写者规则见根 manifest）。
- 改 mapper 函数名/签名要同步 `tests/` 的 monkeypatch 字符串目标（按「查找处」解析，指错模块不报错、假件静默失效）。

## Dependencies And Collaboration

- 依赖 [`../engine/memory/storage/database.py`](../engine/memory/storage/database.py) 的 `MemoryDB`；被 `service/` 独占消费。

## Investigation Rule

1. 数据问题先跑 SQL 本身核对表内容，再看 mapper 的 WHERE 守卫，最后看调用方的失败分支。
2. 并发写问题优先怀疑「没包事务」或「守卫写在 WHERE 而非 JOIN」。

## Core Commands

```bash
/opt/miniconda3/envs/biopilot/bin/python -m pytest tests/rag -q
```

## Verification

```bash
/opt/miniconda3/envs/biopilot/bin/python -m pytest tests/rag tests/api -q
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- 同层：[`../service/`](../service/AGENTS.md)（唯一消费方）

## References

- [`../engine/memory/storage/database.py`](../engine/memory/storage/database.py)（连接、事务、`_SCHEMA`）
