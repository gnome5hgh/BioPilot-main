package com.biopilot.skill.service.impl;

import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.skill.domain.BioSkill;
import com.biopilot.skill.dto.InspectResult;
import com.biopilot.skill.dto.SkillDetail;
import com.biopilot.skill.dto.SkillInfo;
import com.biopilot.skill.dto.SkillView;
import com.biopilot.skill.mapper.BioSkillMapper;
import com.biopilot.skill.service.SkillService;
import com.biopilot.skill.support.SkillArchive;
import com.biopilot.skill.support.SkillFetcher;
import com.biopilot.skill.support.SkillPackageValidator;
import com.biopilot.skill.support.SkillStaging;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 技能管理的实现。
 *
 * <p>一致性约定（按「中断只留可自动清扫的孤儿对象，绝不留死行」定序）：</p>
 * <ul>
 *   <li>安装：先把对象写入 OSS（键含内容 sha，天然幂等），再在事务内写行；
 *       写行失败补偿删除本次新写对象。</li>
 *   <li>更新：先写新对象，再事务内换行，提交后尽力删除旧对象。</li>
 *   <li>卸载：先事务删行，再尽力删对象（平台既有方向）；孤儿对象可后台清扫。</li>
 * </ul>
 */
@Service
public class SkillServiceImpl implements SkillService {

    private static final String SOURCE_META = "source-meta.json";

    private final BioSkillMapper mapper;
    private final MinioTemplate minio;
    private final SkillPackageValidator validator;
    private final SkillFetcher fetcher;
    private final SkillArchive archive;
    private final SkillStaging staging;
    private final TransactionTemplate transaction;
    private final ObjectMapper json = new ObjectMapper();

    public SkillServiceImpl(BioSkillMapper mapper, MinioTemplate minio,
                            SkillPackageValidator validator, SkillFetcher fetcher,
                            SkillArchive archive, SkillStaging staging,
                            TransactionTemplate transaction) {
        this.mapper = mapper;
        this.minio = minio;
        this.validator = validator;
        this.fetcher = fetcher;
        this.archive = archive;
        this.staging = staging;
        this.transaction = transaction;
    }

    @Override
    public List<SkillView> list(long userId) {
        return mapper.selectList(Wrappers.<BioSkill>lambdaQuery()
                        .orderByDesc(BioSkill::getInstalledAt))
                .stream().map(this::toView).toList();
    }

    @Override
    public SkillDetail detail(long userId, String name) {
        BioSkill row = require(userId, name);
        byte[] zip = minio.getObject(row.getOssKey());
        String content = SkillFetcher.readSkillMarkdown(zip);
        return new SkillDetail(row.getName(), row.getDescription(), row.getVersion(),
                row.getSource(), row.getSourceUrl(), row.getSourceRef(),
                row.getEnabled() != null && row.getEnabled() == 1,
                row.getInstalledAt(), content);
    }

    @Override
    public InspectResult inspectGit(long userId, String source, String ref) {
        String stagingId = staging.create(userId);
        try {
            Path work = staging.dir(userId, stagingId);
            SkillFetcher.Fetched fetched = fetcher.fetchGit(source, ref, work);
            writeSourceMeta(work, Map.of(
                    "type", "git",
                    "url", fetched.url(),
                    "ref", fetched.ref() == null ? "" : fetched.ref(),
                    "sha", fetched.sha()));
            return new InspectResult(stagingId, collect(fetched.root()));
        } catch (RuntimeException e) {
            staging.delete(userId, stagingId);
            throw e;
        }
    }

    @Override
    public InspectResult inspectZip(long userId, byte[] data) {
        String stagingId = staging.create(userId);
        try {
            Path work = staging.dir(userId, stagingId);
            Path root = fetcher.extractZip(data, work);
            writeSourceMeta(work, Map.of("type", "archive"));
            return new InspectResult(stagingId, collect(root));
        } catch (RuntimeException e) {
            staging.delete(userId, stagingId);
            throw e;
        }
    }

    @Override
    public List<SkillView> install(long userId, String stagingId) {
        Path work = staging.dir(userId, stagingId);
        if (!Files.isDirectory(work)) {
            throw new ServiceException(422, "安装会话已过期，请重新预览");
        }
        Path root = Files.isDirectory(work.resolve("src"))
                ? work.resolve("src") : work.resolve("repo");
        List<Path> dirs = fetcher.discoverSkillDirs(root);
        if (dirs.isEmpty()) {
            throw new ServiceException(422, "来源中未发现技能（需要包含 SKILL.md）");
        }
        Map<String, String> source = readSourceMeta(work);

        // 全量准入与冲突预检：任何一项不过都不产生副作用
        List<Prepared> prepared = new ArrayList<>();
        Set<String> names = new HashSet<>();
        for (Path dir : dirs) {
            SkillInfo info = validator.inspect(dir);
            if (!names.add(info.name())) {
                throw new ServiceException(422, "同一来源包含重名技能: " + info.name());
            }
            Long exists = mapper.selectCount(Wrappers.<BioSkill>lambdaQuery()
                    .eq(BioSkill::getName, info.name()));
            if (exists != null && exists > 0) {
                throw new ServiceException(409, "技能已安装，请先卸载: " + info.name());
            }
            byte[] zip = archive.zipDirContents(dir);
            String sha = archive.sha256(zip);
            prepared.add(new Prepared(info, zip, sha, ossKey(userId, info.name(), sha),
                    source.getOrDefault("type", "archive"),
                    blankToNull(source.get("url")),
                    blankToNull(source.get("ref")),
                    blankToNull(source.get("sha"))));
        }

        // 对象先落：内容寻址键让重复写入幂等；行写失败时补偿删除本次新写对象
        for (Prepared p : prepared) {
            minio.putObject(p.key(), p.zip(), "application/zip");
        }
        try {
            transaction.executeWithoutResult(status -> {
                String now = Instant.now().toString();
                for (Prepared p : prepared) {
                    BioSkill row = new BioSkill();
                    row.setUserId(String.valueOf(userId));
                    row.setName(p.info().name());
                    row.setDescription(p.info().description());
                    row.setVersion(p.info().version());
                    row.setSource(p.sourceType());
                    row.setSourceUrl(p.sourceUrl());
                    row.setSourceRef(p.sourceRef());
                    row.setSourceSha(p.sourceSha());
                    row.setOssKey(p.key());
                    row.setContentSha(p.sha());
                    row.setEnabled(1);
                    row.setInstalledAt(now);
                    mapper.insert(row);
                }
            });
        } catch (RuntimeException e) {
            for (Prepared p : prepared) {
                try {
                    minio.removeObject(p.key());
                } catch (RuntimeException ignored) {
                    // 补偿失败只留孤儿对象，不覆盖原始异常
                }
            }
            throw e;
        }
        staging.delete(userId, stagingId);
        return list(userId);
    }

    @Override
    public SkillView toggle(long userId, String name, boolean enabled) {
        BioSkill row = require(userId, name);
        row.setEnabled(enabled ? 1 : 0);
        mapper.updateById(row);
        return toView(row);
    }

    @Override
    public SkillView update(long userId, String name) {
        BioSkill row = require(userId, name);
        if (!"git".equals(row.getSource())) {
            throw new ServiceException(422, "仅 git 来源的技能支持检查更新");
        }
        String stagingId = staging.create(userId);
        try {
            Path work = staging.dir(userId, stagingId);
            SkillFetcher.Fetched fetched =
                    fetcher.fetchGit(row.getSourceUrl(), row.getSourceRef(), work);
            Path target = fetcher.discoverSkillDirs(fetched.root()).stream()
                    .filter(dir -> name.equals(validator.inspect(dir).name()))
                    .findFirst()
                    .orElseThrow(() -> new ServiceException(422, "上游未找到同名技能: " + name));
            SkillInfo info = validator.inspect(target);
            byte[] zip = archive.zipDirContents(target);
            String sha = archive.sha256(zip);
            String newKey = ossKey(userId, name, sha);
            String oldKey = row.getOssKey();

            minio.putObject(newKey, zip, "application/zip");
            try {
                transaction.executeWithoutResult(status -> {
                    row.setDescription(info.description());
                    row.setVersion(info.version());
                    row.setSourceUrl(fetched.url());
                    row.setSourceRef(fetched.ref());
                    row.setSourceSha(fetched.sha());
                    row.setOssKey(newKey);
                    row.setContentSha(sha);
                    row.setInstalledAt(Instant.now().toString());
                    mapper.updateById(row);
                });
            } catch (RuntimeException e) {
                try {
                    minio.removeObject(newKey);
                } catch (RuntimeException ignored) {
                    // 补偿失败只留孤儿对象
                }
                throw e;
            }
            if (oldKey != null && !oldKey.equals(newKey)) {
                try {
                    minio.removeObject(oldKey);
                } catch (RuntimeException ignored) {
                    // 行已提交；旧对象删除失败只留孤儿
                }
            }
            return toView(row);
        } finally {
            staging.delete(userId, stagingId);
        }
    }

    @Override
    public void delete(long userId, String name) {
        BioSkill row = require(userId, name);
        transaction.executeWithoutResult(status -> mapper.deleteById(row.getId()));
        try {
            minio.removeObject(row.getOssKey());
        } catch (RuntimeException ignored) {
            // 行已删；对象删除失败只留孤儿，可后台按前缀对账
        }
    }

    @Override
    public SkillPackage packageForUser(String userId, String name) {
        BioSkill row = mapper.selectForAgent(userId, name);
        if (row == null) {
            throw new ServiceException(404, "技能不存在");
        }
        return new SkillPackage(minio.getObject(row.getOssKey()), row.getContentSha());
    }

    /** 取当前用户的行；不存在即 404（租户插件保证只能取到本人行）。 */
    private BioSkill require(long userId, String name) {
        BioSkill row = mapper.selectOne(Wrappers.<BioSkill>lambdaQuery()
                .eq(BioSkill::getName, name));
        if (row == null) {
            throw new ServiceException(404, "技能不存在: " + name);
        }
        return row;
    }

    /** 发现并校验来源内的全部技能目录。 */
    private List<SkillInfo> collect(Path root) {
        List<Path> dirs = fetcher.discoverSkillDirs(root);
        if (dirs.isEmpty()) {
            throw new ServiceException(422, "来源中未发现技能（需要包含 SKILL.md）");
        }
        List<SkillInfo> infos = new ArrayList<>();
        for (Path dir : dirs) {
            infos.add(validator.inspect(dir));
        }
        return infos;
    }

    /**
     * 把 inspect 阶段确认的来源元数据写进 staging，供 install 落库使用。
     *
     * <p>不能放内存：预览与确认是两次独立请求，staging 目录是两者之间唯一的载体。</p>
     */
    private void writeSourceMeta(Path work, Map<String, String> meta) {
        try {
            Files.createDirectories(work);
            json.writeValue(work.resolve(SOURCE_META).toFile(), meta);
        } catch (IOException e) {
            throw new IllegalStateException("写入暂存元数据失败", e);
        }
    }

    private Map<String, String> readSourceMeta(Path work) {
        Path file = work.resolve(SOURCE_META);
        if (!Files.isRegularFile(file)) {
            return Map.of();
        }
        try {
            String text = Files.readString(file, StandardCharsets.UTF_8);
            return json.readValue(text, new TypeReference<LinkedHashMap<String, String>>() {
            });
        } catch (IOException e) {
            throw new IllegalStateException("读取暂存元数据失败", e);
        }
    }

    private String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }

    private String ossKey(long userId, String name, String sha) {
        return "users/" + userId + "/skills/" + name + "/" + sha + ".zip";
    }

    private SkillView toView(BioSkill row) {
        return new SkillView(row.getName(), row.getDescription(), row.getVersion(),
                row.getSource(), row.getSourceUrl(), row.getSourceRef(),
                row.getEnabled() != null && row.getEnabled() == 1,
                row.getInstalledAt());
    }

    /** 安装前的打包结果（对象内容、指纹与来源元数据）。 */
    private record Prepared(SkillInfo info, byte[] zip, String sha, String key,
                            String sourceType, String sourceUrl, String sourceRef,
                            String sourceSha) {
    }
}
