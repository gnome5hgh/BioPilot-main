# bio-admin

## Scope

- 覆盖 `server/bio-admin/`：SpringBoot 应用入口与全服务端集成测试。
- 业务规则都在各 bio-modules/bio-common 模块自己的 manifest 里；本模块**只有装配，没有业务**。

## Module Positioning

- 角色：`app-manifest-dir`
- 职责：启动类 + 健康检查 + `application.yaml`（SpringBoot 侧配置唯一落点）+ 聚合全部模块的集成测试。

## Directory Structure

- `main/java/.../BioPilotApplication.java` — 启动类（组件扫描聚合全部模块）
- `main/java/.../controller/HealthController.java` — 健康探测
- `main/resources/application.yaml` — 数据源/adapter-base/internal-token/MinIO 等 SpringBoot 侧配置
- `test/java/...` — **全服务端的集成测试都住这里**（按业务域分文件，不按被测模块分工程）

## Core Logic

- **纯装配**：不放业务逻辑、不放公共工具；模块间协作的规则（接口 + impl、只调对方接口）见 [`../AGENTS.md`](../AGENTS.md)。
- **集成测试约定**：直连 compose 的 `biopilot_test` 库（3307）；表结构随实体演进，`@BeforeEach` 内联「DROP + CREATE」保持与实体一致；外部依赖（MinioTemplate、AgentInternalClient）一律 `@MockBean`；用 `@Order` 控制同注册/登录态用例的先后。
- 测试里造 KB 数据：`bio_file` 只造身份与勾选列，索引状态造在引擎的 `bio_rag_paper_status`（与生产单写者一致）。

## Usage And Change Notes

- 启动：`cd bio-admin && mvn spring-boot:run`（8080）。**不要**用 `mvn spring-boot:run -pl bio-admin -am`——直接目标调用会在 reactor 每个模块上执行，库模块没有 main class 必失败。
- 改任何模块的表结构/接口后，跑本模块测试就是全服务端的回归：`mvn test -pl bio-admin`。
- 新增模块要在启动类的扫描范围内（默认同根包 `com.biopilot`），并进 `bio-admin` 的依赖。

## Investigation Rule

1. 启动失败：先看 MySQL 容器健康与 `application.yaml` 的 DSN，再看适配层（8300）是否已就绪（引擎先于 Java 起）。
2. 测试失败：先看是断言失败（行为变了）还是 500（多半是内联 DDL 与实体列不同步）。

## Core Commands

```bash
cd server
cd bio-admin && mvn spring-boot:run   # 启动 8080
mvn test -pl bio-admin                # 全服务端集成测试
```

## Verification

```bash
cd server && mvn test -pl bio-admin
```

## Routing

- 上级：[`../AGENTS.md`](../AGENTS.md)
- 被装配的模块：[`../bio-modules/`](../bio-modules/) 各域（各有 manifest）与 [`../bio-common/`](../bio-common/AGENTS.md)

## References

- [`src/main/resources/application.yaml`](src/main/resources/application.yaml)
