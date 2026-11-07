package com.biopilot.file.domain;

/** 论文索引状态（引擎表 {@code bio_rag_paper_status} 的只读投影）。

    唯一落点与写者都在引擎侧；文件管理页的论文清单跨栈只读本表用于展示，
    未落行的论文等价于「未进入索引流程」。
*/
public class PaperIndexStatus {

    private String paperId;
    private Integer indexed;
    private String indexStatus;
    private String indexError;
    private String indexedAt;
    private Integer chunkCount;

    public String getPaperId() {
        return paperId;
    }

    public void setPaperId(String paperId) {
        this.paperId = paperId;
    }

    public Integer getIndexed() {
        return indexed;
    }

    public void setIndexed(Integer indexed) {
        this.indexed = indexed;
    }

    public String getIndexStatus() {
        return indexStatus;
    }

    public void setIndexStatus(String indexStatus) {
        this.indexStatus = indexStatus;
    }

    public String getIndexError() {
        return indexError;
    }

    public void setIndexError(String indexError) {
        this.indexError = indexError;
    }

    public String getIndexedAt() {
        return indexedAt;
    }

    public void setIndexedAt(String indexedAt) {
        this.indexedAt = indexedAt;
    }

    public Integer getChunkCount() {
        return chunkCount;
    }

    public void setChunkCount(Integer chunkCount) {
        this.chunkCount = chunkCount;
    }
}
