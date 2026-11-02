# bio-common-pdf

## Scope

- PDF 标题与书目元数据提取：PDFBox 读首页版面/文档信息，DOI/arXiv → CrossRef/OpenAlex。
- 平台论文标题的**唯一来源**：`bio_paper.title` 由本模块产出；Python 只消费。

## Module Positioning

- 角色：`shared-capability`
- 职责：`PdfTitleExtractor`（元数据标题 + 首页字号启发式）、`PdfIdentifierExtractor`、`BibliographyClient`、`PdfMetadataExtractor`。
- 不依赖 OSS：入参是 PDF 字节，由调用方从 MinIO 取。

## Core Logic

- 标题判据「宁空勿错」：明确不是标题的形态一律拒绝；取不到就空，绝不回退文件名。
- `extractTitle` 只做本地判断（上传同步路径用）；`extract` 额外查外部书目（加入引用库时用）。
- 网络失败/查不到一律留空，不抛给调用方。

## Dependencies And Collaboration

- 被 `bio-catalog`（上传/登记）与 `bio-citation`（from-paper）使用。
