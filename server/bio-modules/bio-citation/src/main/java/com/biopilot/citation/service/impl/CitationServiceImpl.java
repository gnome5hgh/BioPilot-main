package com.biopilot.citation.service.impl;

import com.biopilot.citation.service.CitationService;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.biopilot.file.domain.BioPaper;
import com.biopilot.file.service.PaperDeletionHook;
import com.biopilot.file.service.PaperMetadataHook;
import com.biopilot.file.service.PaperService;
import com.biopilot.citation.domain.BioCitation;
import com.biopilot.citation.dto.CitationView;
import com.biopilot.citation.mapper.BioCitationMapper;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.common.pdf.PaperMeta;
import com.biopilot.common.pdf.PdfMetadataExtractor;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.biopilot.citation.service.CitationKeyGenerator;
import com.biopilot.citation.service.CitationFormatter;

/** 平台引用库：用户从文件管理加入论文、维护库外条目、导出 .bib。

    引用行与论文通过 `bio_paper.citation_id` 单向关联；加入/移出/论文删除都在
    同一事务里维护两侧状态（数据库外键存在时 `ON DELETE SET NULL` 兜底）。
*/
@Service
public class CitationServiceImpl implements CitationService, PaperDeletionHook, PaperMetadataHook {

    private static final String SOURCE_PAPER = "paper";
    private static final String SOURCE_EXTERNAL = "external";

    private final BioCitationMapper mapper;
    private final PaperService papers;
    private final MinioTemplate minio;
    private final PdfMetadataExtractor metadata;

    public CitationServiceImpl(BioCitationMapper mapper, PaperService papers,
                           MinioTemplate minio, PdfMetadataExtractor metadata) {
        this.mapper = mapper;
        this.papers = papers;
        this.minio = minio;
        this.metadata = metadata;
    }

    /** 列表/搜索：按标题、作者、key 的子串匹配（空查询返回全部）。 */
    public List<CitationView> list(String q) {
        String text = q == null ? "" : q.trim().toLowerCase(Locale.ROOT);
        return mapper.selectList(new QueryWrapper<BioCitation>().orderByAsc("seq"))
                .stream()
                .filter(row -> text.isEmpty() || matches(row, text))
                .map(CitationView::from)
                .toList();
    }

    /** 按样式渲染指定 key（未知 key 静默跳过）。 */
    public String format(List<String> keys, String style) {
        List<BioCitation> rows = new ArrayList<>();
        if (keys != null) {
            for (String key : keys) {
                BioCitation row = getByKey(key);
                if (row != null) {
                    rows.add(row);
                }
            }
        }
        return CitationFormatter.format(rows, style);
    }

    /** 导出当前用户全部条目为 .bib 文本。 */
    public String export() {
        return CitationFormatter.format(
                mapper.selectList(new QueryWrapper<BioCitation>().orderByAsc("seq")),
                "bibtex");
    }

    /** 从文件管理里的论文加入引用库（幂等：已加入直接返回）。
     *
     * Args:
     *     userId: 归属用户。
     *     paperId: 论文 id。
     *
     * Returns:
     *     CitationView: 引用条目。
     */
    @Transactional
    public CitationView fromPaper(long userId, String paperId) {
        BioPaper paper = papers.getForUpdate(userId, paperId);
        if (paper.getCitationId() != null && !paper.getCitationId().isBlank()) {
            BioCitation existing = mapper.selectById(paper.getCitationId());
            if (existing != null) {
                return CitationView.from(existing);
            }
            papers.linkCitation(userId, paperId, null);
        }
        PaperMeta meta = new PaperMeta(paper.getTitle(), paper.getAuthors(),
                paper.getYear(), paper.getJournal(), "", "article");
        if (isBlank(meta.title()) || isBlank(meta.authors())
                || isBlank(meta.year()) || isBlank(meta.journal())) {
            try {
                byte[] data = minio.getObject(paper.getOssKey());
                meta = meta.merge(metadata.extract(data));
            } catch (RuntimeException ignored) {
                // 取不到原文就用已有字段；标题为空才拒绝入库
            }
        }
        if (isBlank(meta.title())) {
            throw new ServiceException(422, "论文标题为空，无法生成引用条目（请先在文件管理补标题）");
        }
        BioCitation row = new BioCitation();
        row.setId(newId());
        row.setUserId(String.valueOf(userId));
        row.setCiteKey(uniqueKey(CitationKeyGenerator.generate(
                meta.title(), meta.authors(), meta.year())));
        row.setEntryType(isBlank(meta.entryType()) ? "article" : meta.entryType());
        row.setTitle(meta.title());
        row.setAuthors(nvl(meta.authors()));
        row.setYear(nvl(meta.year()));
        row.setJournal(nvl(meta.journal()));
        row.setDoi(nvl(meta.doi()));
        row.setSource(SOURCE_PAPER);
        row.setCreatedAt(now());
        mapper.insert(row);
        papers.linkCitation(userId, paperId, row.getId());
        return CitationView.from(row);
    }

    /** 文件管理页按 paper_id 移出引用库。
     *
     * Returns:
     *     bool: 是否移除了条目。
     */
    @Transactional
    public boolean removeByPaper(long userId, String paperId) {
        BioPaper paper = papers.get(userId, paperId);
        if (paper.getCitationId() == null || paper.getCitationId().isBlank()) {
            return false;
        }
        mapper.deleteById(paper.getCitationId());
        papers.linkCitation(userId, paperId, null);
        return true;
    }

    /** 按 key 删除条目。 */
    @Transactional
    public boolean remove(String key) {
        BioCitation row = getByKey(key);
        if (row == null) {
            return false;
        }
        mapper.deleteById(row.getId());
        papers.clearCitationByCitationId(row.getId());
        return true;
    }

    /** 库外条目手工新增。 */
    @Transactional
    public CitationView addExternal(long userId, Map<String, Object> body) {
        String title = value(body, "title");
        if (title.isBlank()) {
            throw new ServiceException(422, "标题不能为空");
        }
        BioCitation row = new BioCitation();
        row.setId(newId());
        row.setUserId(String.valueOf(userId));
        row.setCiteKey(uniqueKey(CitationKeyGenerator.generate(
                title, value(body, "authors"), value(body, "year"))));
        apply(row, body);
        row.setSource(SOURCE_EXTERNAL);
        row.setCreatedAt(now());
        mapper.insert(row);
        return CitationView.from(row);
    }

    /** 库外条目编辑（key 不变）。 */
    @Transactional
    public CitationView updateExternal(String key, Map<String, Object> body) {
        BioCitation row = getByKey(key);
        if (row == null) {
            throw new ServiceException(404, "引用条目不存在");
        }
        apply(row, body);
        mapper.update(null, new LambdaUpdateWrapper<BioCitation>()
                .eq(BioCitation::getId, row.getId())
                .set(BioCitation::getEntryType, row.getEntryType())
                .set(BioCitation::getTitle, row.getTitle())
                .set(BioCitation::getAuthors, row.getAuthors())
                .set(BioCitation::getYear, row.getYear())
                .set(BioCitation::getJournal, row.getJournal())
                .set(BioCitation::getVolume, row.getVolume())
                .set(BioCitation::getPages, row.getPages())
                .set(BioCitation::getDoi, row.getDoi()));
        return CitationView.from(row);
    }

    @Override
    public void onPaperDeleted(long userId, String paperId, String citationId) {
        if (!isBlank(citationId)) {
            mapper.deleteById(citationId);
        }
    }

    @Override
    public void onPaperMetadataChanged(String citationId, String title, String authors,
                                       String year, String journal) {
        if (isBlank(citationId)) {
            return;
        }
        mapper.update(null, new LambdaUpdateWrapper<BioCitation>()
                .eq(BioCitation::getId, citationId)
                .set(BioCitation::getTitle, title)
                .set(BioCitation::getAuthors, authors)
                .set(BioCitation::getYear, year)
                .set(BioCitation::getJournal, journal));
    }

    private BioCitation getByKey(String key) {
        if (key == null || key.isBlank()) {
            return null;
        }
        return mapper.selectOne(new LambdaQueryWrapper<BioCitation>()
                .eq(BioCitation::getCiteKey, key));
    }

    private String uniqueKey(String base) {
        String candidate = base.isBlank() ? "paper" : base;
        int n = 1;
        while (getByKey(candidate) != null) {
            n += 1;
            candidate = base + n;
        }
        return candidate;
    }

    private boolean matches(BioCitation row, String text) {
        return contains(row.getTitle(), text) || contains(row.getAuthors(), text)
                || contains(row.getCiteKey(), text);
    }

    private boolean contains(String value, String text) {
        return value != null && value.toLowerCase(Locale.ROOT).contains(text);
    }

    private void apply(BioCitation row, Map<String, Object> body) {
        row.setEntryType(blankTo(value(body, "entry_type"), "article"));
        row.setTitle(value(body, "title"));
        row.setAuthors(value(body, "authors"));
        row.setYear(value(body, "year"));
        row.setJournal(value(body, "journal"));
        row.setVolume(value(body, "volume"));
        row.setPages(value(body, "pages"));
        row.setDoi(value(body, "doi"));
    }

    private String value(Map<String, Object> body, String key) {
        if (body == null) {
            return "";
        }
        Object value = body.get(key);
        return value == null ? "" : String.valueOf(value).trim();
    }

    private String blankTo(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value;
    }

    private String nvl(String value) {
        return value == null ? "" : value;
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private String newId() {
        return UUID.randomUUID().toString().replace("-", "");
    }

    private String now() {
        return OffsetDateTime.now(ZoneOffset.UTC).toString();
    }
}
