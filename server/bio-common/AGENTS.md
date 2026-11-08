# bio-common

## Scope

- 覆盖 `server/bio-common/`：后端共享基础设施聚合层，目录结构对齐 `cde-base/cde-common`。
- 业务模块与应用入口通过 Maven 依赖引入所需能力，禁止复制 common 代码。

## Module Positioning

- 角色：`aggregator-manifest-dir`
- 职责：按技术关注点拆分共享能力；每个子模块只封装一个关注点。

## Directory Structure

- `bio-common-core/` — R / PageResult / ServiceException / 常量 / 通用工具；不依赖 Web/MyBatis/Sa-Token/MinIO（有 manifest）
- `bio-common-web/` — GlobalExceptionHandler / InternalHttp / MultipartRelay / SseRelay（有 manifest）
- `bio-common-mybatis/` — MyBatis-Plus 配置、租户插件、分页与基础实体（有 manifest）
- `bio-common-satoken/` — Sa-Token 配置、401/403 异常映射（有 manifest）
- `bio-common-oss/` — MinIO 客户端与 `biopilot.storage.minio` 配置（有 manifest）
- `bio-common-pdf/` / `bio-common-net/` / `bio-common-mcp/` — 平台连接器（各有 manifest）

## Core Logic

- **依赖方向**：`core ← web/mybatis/satoken/oss`；业务模块只依赖 common，不依赖其他模块的 mapper/entity。
- **异常 advice 有顺序**：具体异常（Sa-Token 401/403）必须排在全局兜底之前。
- **新共享能力先确认是否已有子模块覆盖**；有则扩展，无则新建并同步 `bio-common/pom.xml` 与根 `server/pom.xml` 的 `dependencyManagement`。
- 修改本层影响面广，必须全量构建与测试。

## Routing

- 上级：[`../../AGENTS.md`](../AGENTS.md)——即 `server/AGENTS.md`
- 子模块 manifest：[`bio-common-core/`](bio-common-core/AGENTS.md) / [`bio-common-web/`](bio-common-web/AGENTS.md) / [`bio-common-mybatis/`](bio-common-mybatis/AGENTS.md) / [`bio-common-satoken/`](bio-common-satoken/AGENTS.md) / [`bio-common-oss/`](bio-common-oss/AGENTS.md) / [`bio-common-pdf/`](bio-common-pdf/AGENTS.md) / [`bio-common-net/`](bio-common-net/AGENTS.md) / [`bio-common-mcp/`](bio-common-mcp/AGENTS.md)

## Core Commands

```bash
cd server
mvn -q -DskipTests install
mvn test -pl bio-admin -q
```
