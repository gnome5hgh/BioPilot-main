# biopilot/common

## Scope

- 覆盖 `biopilot/common/`：**跨层共享的基础设施与纯函数**，对应后端工程里的 common 层（参考 `cde-common-core`）。
- 只放「没有业务归属、又被两个以上消费方使用」的东西；判据是消费方数量，不是重要性。

## Module Positioning

- 角色：`shared-infrastructure`
- 职责：提供常量、枚举、通用工具、存储原语与出站平台客户端，让 core / tools / webapi 不必各写一份。
- 不承载 BioPilot 业务规则，不认识 `Agent`、`BlockManager`、论文目录、调度任务等业务对象。

## Directory Structure

```text
common/
├─ core/
│  ├─ constants/      # 跨层共享取值与枚举（MessageRole、RETRY_BACKOFF_BASE）
│  └─ utils/          # text / tokenization / frontmatter 等纯函数
├─ platform/          # 出站平台边界：调 Java `/internal/*` 的唯一客户端
└─ storage/           # 通用存储原语（atomic 写）
```

## Core Logic

- **依赖方向**：本包不得 import `core` / `tools` / `webapi` / `cli`；它是最底层。
- **只放纯函数与数据**：出现业务判断，说明它该去 `core`；平台文件管理（上传/列表/删除/键约定）归 Java。
- **共享判据是消费方数量**：只有一个消费方的实现留在原处；为了「整齐」搬进来会让这里退化成杂物间。
- **常量两级布局**：枚举放 `core/constants/enums/<name>.py`（一个枚举一个文件），其余放同层 `constants.py`；`__init__.py` 只做再导出。
- **存储原语仅限通用能力**：只剩本地原子写；对象存储的读写一律经 `platform` 调 Java，或由引擎组件自己的内部存储（图表原图、工具结果外置）持有。
- **`platform/` 是唯一出站实现**：header、超时与错误映射只写一份；它可以依赖 `httpx`，这是本包「只依赖标准库」的唯一例外。

## Dependencies And Collaboration

- 被 `core/`、`tools/`、`webapi/`、`cli/` 消费。
- 本包只依赖标准库，唯一例外是 `platform/` 的 `httpx`；新增第三方依赖前先确认是否真的需要跨层共享。

## Investigation Rule

1. 排查「两处算法不一致」先确认是否有一处绕过了这里的单点实现。
2. 想知道某段通用逻辑的归宿，先看本包；业务语义的去 `core`/`adapters`。
3. 文档与代码冲突时以代码事实为准。

## Core Commands

```bash
/opt/miniconda3/envs/biopilot/bin/python -m pytest tests/core -q
```
