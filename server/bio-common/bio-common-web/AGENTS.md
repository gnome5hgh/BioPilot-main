# bio-common-web

## Scope

- 覆盖 `server/bio-common/bio-common-web/`：Web 层共享件——全局异常兜底、内部调用客户端、中继（multipart/SSE）、内部端点令牌过滤。
- Sa-Token 的登录过滤与鉴权异常映射在 [`../bio-common-satoken/`](../bio-common-satoken/AGENTS.md)。

## Module Positioning

- 角色：`shared-package-manifest-dir`
- 职责：所有控制器共享的横切 Web 行为，业务模块不各自写异常兜底或内部 HTTP 客户端。

## Directory Structure

- `web/handler/GlobalExceptionHandler.java` — 未捕获异常兜底（未映射路径 404、方法不支持 405、超限 413，不许吞成 500）
- `web/http/AgentInternalClient.java` — 调 Python `/internal/**` 的客户端（fire-and-forget，失败只记日志不回滚业务行）
- `web/http/InternalTokenFilter.java` — `/internal/**` 的 `X-Internal-Token` 把关（配置了必须匹配；未配置只放行回环来源）
- `web/http/MultipartRelay.java` / `SseRelay.java` — 浏览器↔引擎的上传与 SSE 中继

## Core Logic

- **内部 HTTP 客户端锁死 HTTP/1.1**：Java HttpClient 默认的 h2c 升级头会被 uvicorn 按协议升级处理并吞掉请求体——任何新建的内部客户端都必须显式 `HTTP_1_1`。
- 异常 advice 有顺序：具体异常（Sa-Token 401/403）先于全局兜底（顺序约定见父 [`../AGENTS.md`](../AGENTS.md)）。
- `AgentInternalClient` 的调用语义是「后台动作」：唤醒索引、触发调度这类失败可重试的操作不抛给调用方。

## Usage And Change Notes

- 新增内部端点调用：加在 `AgentInternalClient`，不另建 client；两端契约（[`../../../biopilot/schema/`](../../../biopilot/schema/AGENTS.md) 的 `internal.py`）同步改。
- 改 `GlobalExceptionHandler` 的映射先确认 404/405/413 语义不变（`server/AGENTS.md` 硬规则）。

## Dependencies And Collaboration

- 依赖 `bio-common-core`；被全部业务模块依赖。
- 与 `bio-common-satoken` 的过滤器/advice 顺序是协作关系，改动任一侧要回归 401/403 路径。

## Core Commands

```bash
cd server && mvn -q -DskipTests install
```

## Verification

```bash
cd server && mvn test -pl bio-admin
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- 兄弟：[`../bio-common-satoken/`](../bio-common-satoken/AGENTS.md) / [`../bio-common-core/`](../bio-common-core/AGENTS.md)

## References

- [`src/main/java/com/biopilot/common/web/http/AgentInternalClient.java`](src/main/java/com/biopilot/common/web/http/AgentInternalClient.java)
