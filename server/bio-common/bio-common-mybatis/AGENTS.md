# bio-common-mybatis

## Scope

- 覆盖 `server/bio-common/bio-common-mybatis/`：MyBatis-Plus 装配、租户插件、分页与基础实体。
- 业务模块里 `*ForAgent` 方法上的 `@InterceptorIgnore(tenantLine="true")` 是**业务侧**的显式豁免选择，本模块只提供机制。

## Module Positioning

- 角色：`shared-package-manifest-dir`
- 职责：行级 `user_id` 过滤的机制化——业务表**不许手写 where 补过滤**，漏一处就是越权读。

## Directory Structure

- `mybatis/config/MybatisPlusConfig.java` — 租户插件（`TenantLineInnerInterceptor`）、分页插件、豁免表登记

## Core Logic

- **租户列是 VARCHAR**：`TenantLineHandler` 的值必须用 `StringValue`——数字字面量会让 MySQL 隐式转换、丢索引还可能误匹配。
- **豁免表显式登记**：无 `user_id` 的全局表（`sys_role`、`bio_oss_gc`）与引擎侧需要跨用户读写的引擎表在插件配置里列名豁免；改豁免清单要对照根 manifest 的单写者规则。
- 引擎表的跨栈只读（如 `bio_rag_paper_status`）走显式 `user_id` 的 SQL（JdbcTemplate/注解 SQL），不进插件。

## Usage And Change Notes

- 新表：默认进租户过滤；要豁免必须在本模块登记并同步 `server/AGENTS.md`。
- 改插件实现后回归点：任一列表接口的行数（多租户串台会在测试里表现为「看到别人的数据」）。

## Dependencies And Collaboration

- 依赖 `bio-common-core`；被业务模块与 `bio-admin` 依赖。
- 与 `bio-common-satoken` 无依赖关系（鉴权在登录态，租户在 SQL 层）。

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
- 兄弟：[`../bio-common-core/`](../bio-common-core/AGENTS.md) / [`../bio-common-web/`](../bio-common-web/AGENTS.md)

## References

- [`src/main/java/com/biopilot/common/mybatis/config/MybatisPlusConfig.java`](src/main/java/com/biopilot/common/mybatis/config/MybatisPlusConfig.java)
