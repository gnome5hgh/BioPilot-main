# bio-common-satoken

## Scope

- 覆盖 `server/bio-common/bio-common-satoken/`：Sa-Token 登录过滤链与鉴权异常映射。
- `/internal/**` 的令牌校验在 [`../bio-common-web/`](../bio-common-web/AGENTS.md) 的 `InternalTokenFilter`，不在这里。

## Module Positioning

- 角色：`shared-package-manifest-dir`
- 职责：登录态的统一入口（哪些路径要登录）与 401/403 的对外语义。

## Directory Structure

- `satoken/config/SaTokenConfigure.java` — 过滤链装配（登录校验、放行清单、`/internal/**` 排除）
- `satoken/handler/SaTokenExceptionAdvice.java` — `NotLoginException`/`NotRoleException` → 401/403

## Core Logic

- **advice 优先级必须高于全局兜底**：`@Order` 取最高优先级，否则 403 被全局异常处理器吞成 500。
- 管理接口的 `@SaCheckRole("ADMIN")` 注解写在各业务控制器，本模块只负责把它变成 403。

## Usage And Change Notes

- 调整放行清单（公开路径）要同步核对前端路由与 `InternalTokenFilter` 的排除范围，别把 `/internal/**` 暴露进登录链。
- 改 401/403 的响应形状要过 `AuthFlowTest`。

## Dependencies And Collaboration

- 依赖 `bio-common-core`；被 `bio-admin` 与各业务模块依赖。
- 与 `bio-common-web` 的顺序约定见父 [`../AGENTS.md`](../AGENTS.md)。

## Core Commands

```bash
cd server && mvn -q -DskipTests install
```

## Verification

```bash
cd server && mvn test -pl bio-admin -Dtest=AuthFlowTest
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- 兄弟：[`../bio-common-web/`](../bio-common-web/AGENTS.md)

## References

- [`src/main/java/com/biopilot/common/satoken/config/SaTokenConfigure.java`](src/main/java/com/biopilot/common/satoken/config/SaTokenConfigure.java)
