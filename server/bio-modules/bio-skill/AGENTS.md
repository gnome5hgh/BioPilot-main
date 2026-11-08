# bio-skill

## Scope

- 覆盖 `server/bio-modules/bio-skill/`：用户技能的管理面——标准包安装准入、启停/更新/卸载、OSS 包存储与引擎取包端点。
- 技能的**运行时消费**（按 `content_sha` 物化缓存、`load_skill` 工具）在 Python 引擎（`engine/skills/`），本模块只写管理状态。

## Module Positioning

- 角色：`business-domain`
- 职责：`bio_skill` 表（带 `user_id`）与 OSS `users/<uid>/skills/<sha>.zip` 的生命周期；引擎只读 `enabled/content_sha` 两列。

## Directory Structure

- `controller/SkillController.java` — 安装/列表/启停/更新/卸载（浏览器端）
- `controller/InternalSkillController.java` — `/internal/skills/{name}/package`（引擎取包）
- `service/` — `SkillService` 接口 + `impl/SkillServiceImpl`（一致性定序的实现）
- `support/` — `SkillPackageValidator`（包准入校验）、`SkillFetcher`/`SkillArchive`/`SkillStaging`（取包/解包/暂存）
- `domain/BioSkill.java` + `mapper/BioSkillMapper.java` — 实体与访问
- `dto/` — 视图与校验产物

## Core Logic

- **一致性定序（按「中断只留可自动清扫的孤儿对象，绝不留死行」）**：安装=对象先落 OSS（键含内容 sha，天然幂等）→ 事务内写行 → 写行失败补偿删本次新对象；更新=先写新对象 → 事务内换行 → 提交后尽力删旧对象；卸载=反序（先删行再删对象）。
- **包准入**：`SkillPackageValidator` 校验标准包结构（agent 包的 `AGENT.md` + `tools.py` 形状）后才允许入库；**不接受 `tools.py` 之外的「加载即执行」扩展**（根硬红线）。
- 同一 `(user_id, name)` 的技能行更新即「换内容」：新 sha 对象覆盖、行上 `content_sha` 变更即触发引擎下次物化。

## Usage And Change Notes

- 改安装/卸载的定序必须保持「失败可清扫」的性质——测试 `SkillFlowTest` 锁的是结果状态，顺序回归要人工推演中断点。
- `content_sha` 是引擎物化的依据：改算法会让全体用户技能重新物化，属可接受代价但要有意识地做。
- 引擎取包端点是内部契约：路径与响应（zip 字节）不改名不版本化。

## Dependencies And Collaboration

- 依赖 `bio-common-core/web/mybatis/satoken/oss`；**不依赖其他业务模块**。
- 被 `bio-admin` 聚合启动；引擎经 `/internal/skills/{name}/package` 单向取包。

## Investigation Rule

1. 技能装不上：先看 `SkillPackageValidator` 的拒绝原因（包结构），再看 OSS 写入与行写入的补偿日志。
2. 引擎侧技能没更新：核对 `bio_skill.content_sha` 与引擎物化缓存的 sha 是否一致。

## Core Commands

```bash
cd server && mvn test -pl bio-admin -Dtest=SkillFlowTest
```

## Verification

```bash
cd server && mvn test -pl bio-admin -Dtest=SkillFlowTest
```

## Routing

- 上级：[`../../AGENTS.md`](../../AGENTS.md)（`bio-modules/` 无聚合 manifest，域间规则以 server 根为准）
- 同层：[`bio-file/`](../bio-file/AGENTS.md)（同类「管理面/消费面」分法的参照）
- 引擎消费侧：[`../../../biopilot/engine/skills/AGENTS.md`](../../../biopilot/engine/skills/AGENTS.md)

## References

- [`src/main/java/com/biopilot/skill/service/impl/SkillServiceImpl.java`](src/main/java/com/biopilot/skill/service/impl/SkillServiceImpl.java)
