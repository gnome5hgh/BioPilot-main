# biopilot/config

## Scope

- 覆盖 `biopilot/config/`：全局可调参数的声明、加载、字段描述与 MySQL 持久化。
- 本目录只管**全局可调参数**；各子包组件自己的行为参数跟组件走（见下）。

## Module Positioning

- 角色：`config-package-manifest-dir`
- 职责：声明全部可调参数及默认值，并按固定优先级把「MySQL 覆盖 → 引导文件 → 环境变量」合并进来；同时给设置页提供字段描述与写入校验。

## Directory Structure

- `__init__.py` — 只做再导出（对外公共面只有 `biopilot.config` 一个）
- `schemas/sections.py` — 配置分区 dataclass 树，**所有可调参数默认值的唯一声明点**
- `services/loader.py` — 加载链（默认值 < `bio_config` < `config.yaml` 引导层 < env）、递归合并、env 派生、路径绝对化
- `services/schema.py` — 字段描述（路径/标签/类型/密钥/重启标识）、引导层白名单、写入校验
- `services/store.py` — `bio_config` / `bio_config_secret` / `bio_config_history` 的读写、AES-GCM 密钥加密、乐观锁、历史回滚、旧 YAML 导入
- `services/cli.py` — `biopilot config import|export|history|rollback` 运维命令

## Responsibilities

- 提供唯一一份参数契约，供所有消费模块读取。
- 运行时配置的真相源是 MySQL；设置页写稀疏覆盖（只存改过的路径），未出现的键回落代码默认值。
- `config.yaml` 只承载「进程启动前必须知道、且跟部署环境绑定」的引导项；测试与离线脚本用 `BIOPILOT_CONFIG_SOURCE=file` 回到纯文件链路。
- 把相对路径在加载出口统一绝对化。

## Core Logic

- **`schemas/sections.py` 是默认值的唯一声明点**：新增可调参数先在这里加字段，消费模块直接读，**不要在模块内另设常量副本**。
- **加载优先级固定为 默认值 < MySQL `bio_config` < `config.yaml` 引导层 < 环境变量**。数据库模式的 `config.yaml` 只合并 `BOOTSTRAP_PATHS`，运行时字段一律以库为准。
- **引导层字段只读**：`runtime.workspace` / `runtime.memory_dsn` / `runtime.agents_dir` / `runtime.user_cache_dir`、`platform.base_url` / `internal_token`、`corpus.analysis_dir` / `research_dir`、`rag.storage.uri` / `collection` / `minio.*`、`compaction.tool_results.local_dir`。它们在启动前就要用到，换部署就会变，设置页只展示、不接受写入。
- **密钥单独加密**：`*.api_key`、`runtime.models`、`platform.internal_token`、`rag.storage.minio.secret_key` 存 `bio_config_secret`，AES-GCM 加密；读取接口只返回「是否已配置 + 末 4 位」，模型清单逐项掩码。主密钥优先取 `BIOPILOT_CONFIG_KEY`，否则用 `<workspace>/config.key`（缺失时首次写入自动生成，0600）。
- **每次保存都留历史**：`bio_config_history` 存整份快照与 `changed_paths`；版本号做乐观锁，设置页冲突返回 409，可按版本回滚。
- **读取降级**：数据库或密钥不可用时，loader 告警后回退到「引导文件 + env」，不因配置库故障让进程起不来；写入路径则严格失败，避免在读不到旧密钥时覆盖它们。
- **`BIOPILOT_MEMORY_MYSQL_DSN` 是 `runtime.memory_dsn` 的规范来源**（与 MemoryDB、start.sh、compose 共用）；显式的 `BIOPILOT_RUNTIME_MEMORY_DSN` 优先。
- **只认标量 env 覆写**：dict / list 只能经设置页的 JSON 编辑器或 YAML（文件模式）配置；嵌套 dataclass 逐层递归。
- **`compaction` 是配置 dataclass**：trigger（tokens/messages/fraction，OR）、keep、摘要参数与 `tool_results` 外置阈值都在 `schemas/sections.py`；消费模块不要再定义默认值副本。
- **环境变量名不另设映射表**，按配置路径派生：`BIOPILOT_` + 路径大写、`_` 连接（`rag.storage.uri` → `BIOPILOT_RAG_STORAGE_URI`）。
- **路径字段在加载出口绝对化**：`workspace` 一类路径在 `from_env()` 末尾解析成绝对路径，其他模块不要再自行拼相对路径。
- **改了要重启的字段**：`rag.*` 与 `platform.search_timeout` / `transfer_timeout` 被进程级单例捕获，设置页标「需重启」；其余字段保存后丢弃 Agent 缓存，下一轮生效。

## Key Entry Points

- `schemas/sections.py` — 参数树与默认值
- `services/loader.py` 的 `BioPilotConfig` — 加载入口（含 `from_env`、`enable_db_source`）
- `services/schema.py` 的 `build_schema` / `validate_patches` — 设置页契约与写入校验
- `services/store.py` 的 `ConfigStore` — MySQL 持久化、加密、历史
- `biopilot/webapi/settings.py` — 设置接口的服务端逻辑
- `biopilot/config/services/cli.py` — `biopilot config import|export|history|rollback`

## Usage And Change Notes

- **两类 `config/` 的判据是「管理员会不会在设置页改」**：会 → 顶层 `biopilot/config/`；不会、只有代码调用点决定 → 跟组件走（各子包自己的 `config/`）。
- **新增或改名参数要同步**：`schemas/sections.py` 的字段、`services/schema.py` 的 `FIELD_META`（标签/说明）与分节布局、引导层参数还要同步 `.env.example` 与根 manifest。不再维护 `config.example.yaml`。
- 新增映射型配置时别指望它能经 env 派生；要它可配就给设置页一个 JSON 编辑器。
- 不要为兼容旧键名留别名分支——这类分支没有消费方、只会让「唯一声明点」失效。

## Dependencies And Collaboration

- 被 `webapi/`（入口与装配）、`core/` 各子包、`tools/` 读取；本包不依赖它们中的任何一个（`store.py` 只依赖 `core/memory/storage/database.py` 的连接池）。
- 存储表归引擎所有：DDL 在 `core/memory/storage/database.py` 的 `_SCHEMA` 里，不在 `server/script/sql/`。

## Investigation Rule

1. 先分清是「参数没生效」还是「默认值不对」：前者看设置页的 `source`（env/db/file/default）与加载优先级，后者看 `schemas/sections.py`。
2. 看当前生效值：`BioPilotConfig.from_env()`（Web 进程内会读数据库）；看字段契约：`build_schema()`。
3. 排查「配置改了没反应」：先看 `source=env`（环境变量压过设置页），再看字段是否标了「需重启」。
4. 文档与代码冲突时以代码事实为准。

## Core Commands

```bash
conda run -n biopilot python -m pytest tests/core -k "config" -q

# 旧配置导入 / 导出 / 历史 / 回滚
biopilot config import config.yaml
biopilot config export
biopilot config history
biopilot config rollback <version>
```

## Verification

```bash
conda run -n biopilot python -m pytest tests/core/test_config.py tests/core/test_config_schema.py tests/core/test_config_store.py -q
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- 装配方：[`../webapi/AGENTS.md`](../webapi/AGENTS.md)
- 设置接口：[`../webapi/AGENTS.md`](../webapi/AGENTS.md)
- 运行层的组件参数：[`../core/AGENTS.md`](../core/AGENTS.md)

## References

- [`schemas/sections.py`](schemas/sections.py)
- [`services/loader.py`](services/loader.py)
- [`services/schema.py`](services/schema.py)
- [`services/store.py`](services/store.py)
- [`../../.env.example`](../../.env.example)
