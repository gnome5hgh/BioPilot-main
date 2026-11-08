# bio-common-core

## Scope

- 覆盖 `server/bio-common/bio-common-core/`：零中间件依赖的通用件（响应包装、分页、异常、纯工具）。
- 需要 Web/MyBatis/Sa-Token/MinIO 的能力放各自子模块，**绝不塞进 core**。

## Module Positioning

- 角色：`shared-package-manifest-dir`
- 职责：被所有模块依赖的最底层；改它会重编一切，所以只放「各域都要、且不碰中间件」的东西。

## Directory Structure

- `core/R.java` — 统一响应包装
- `core/page/PageResult.java` — 分页包装
- `core/exception/ServiceException.java` — 业务失败（带 HTTP status，由全局兜底转文案）
- `core/text/TitleNormalizer.java` — 论文标题归一化（入库匹配/去重用；与 Python 侧的同名工具数据永不相交，各自独立演化）

## Core Logic

- 依赖方向的最底端：**不依赖** web/mybatis/satoken/oss 任何子模块（见父 [`../AGENTS.md`](../AGENTS.md)）。
- 异常语义的约定：业务失败抛 `ServiceException`（带文案），由 `bio-common-web` 的全局兜底转 `R.fail`。

## Usage And Change Notes

- 新增通用能力前先确认别的子模块没覆盖；能放 core 的判据是「纯函数 + 零依赖」。
- 改 `R`/`PageResult` 的字段形状会波及全部控制器响应——先全局搜消费方。

## Dependencies And Collaboration

- 被所有 server 模块依赖；不依赖任何兄弟子模块。

## Core Commands

```bash
cd server && mvn -q -DskipTests install
```

## Verification

```bash
cd server && mvn -q -DskipTests install && mvn test -pl bio-admin
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- 兄弟：[`../bio-common-web/`](../bio-common-web/AGENTS.md)（异常兜底的实现方）

## References

- [`src/main/java/com/biopilot/common/core/text/TitleNormalizer.java`](src/main/java/com/biopilot/common/core/text/TitleNormalizer.java)
