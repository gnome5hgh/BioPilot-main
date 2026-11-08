# bio-common-oss

## Scope

- 覆盖 `server/bio-common/bio-common-oss/`：MinIO 客户端与对象存储配置。
- 「对象先落、行后写；删除反向」的一致性方向是各业务模块的职责（`bio-file`/`bio-skill`），本模块只提供原子操作。

## Module Positioning

- 角色：`shared-package-manifest-dir`
- 职责：对象存储的统一出入口——业务模块不各自拼 MinIO SDK。

## Directory Structure

- `oss/core/MinioTemplate.java` — put/get/remove/listKeys 等原子操作
- `oss/config/MinioConfig.java` + `MinioProperties.java` — `biopilot.storage.minio` 配置（endpoint/access key/bucket）

## Core Logic

- 单应用桶 `biopilot`，前缀即隔离与清理边界：平台文件 `users/<uid>/…`、图表原图 `rag/images/…`（布局详见根 manifest 与 ADR 0012）。
- 模板方法返回原始字节/键，不做归属校验——`(user_id, id)` 归属检查是调用方（内部端点控制器）的职责。

## Usage And Change Notes

- 新增对象类别：先定前缀（清理边界跟着前缀走），再定写序（一致性方向不许反）。
- 改 `MinioTemplate` 方法签名要全局搜消费方（bio-file/bio-skill/engine 的 image_store 都可能用到）。

## Dependencies And Collaboration

- 依赖 `bio-common-core`；被 `bio-file`、`bio-skill` 等模块依赖。
- 引擎侧的图表原图与工具结果由 Python 自己的存储客户端持有（数据域不相交），不共用本模块。

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
- 兄弟：[`../bio-common-core/`](../bio-common-core/AGENTS.md)
- 消费方：[`../../bio-modules/bio-file/`](../../bio-modules/bio-file/AGENTS.md) / [`../../bio-modules/bio-skill/`](../../bio-modules/bio-skill/AGENTS.md)

## References

- [`src/main/java/com/biopilot/common/oss/core/MinioTemplate.java`](src/main/java/com/biopilot/common/oss/core/MinioTemplate.java)
