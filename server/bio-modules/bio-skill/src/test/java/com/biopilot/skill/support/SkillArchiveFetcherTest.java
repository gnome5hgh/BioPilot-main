package com.biopilot.skill.support;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.biopilot.common.core.exception.ServiceException;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 打包/解包/发现：确定性、内容哈希、路径穿越与压缩炸弹闸门。 */
class SkillArchiveFetcherTest {

    private final SkillArchive archive = new SkillArchive();
    private final SkillFetcher fetcher = new SkillFetcher();

    @Test
    void zipIsDeterministicAndShaStable(@TempDir Path dir) throws Exception {
        Path skill = Files.createDirectories(dir.resolve("demo"));
        Files.writeString(skill.resolve("SKILL.md"),
                "---\nname: demo\ndescription: x\n---\nbody", StandardCharsets.UTF_8);
        Files.createDirectories(skill.resolve("references"));
        Files.writeString(skill.resolve("references/b.md"), "B", StandardCharsets.UTF_8);
        Files.writeString(skill.resolve("references/a.md"), "A", StandardCharsets.UTF_8);

        byte[] first = archive.zipDirContents(skill);
        byte[] second = archive.zipDirContents(skill);

        assertThat(first).isEqualTo(second);
        assertThat(archive.sha256(first)).isEqualTo(archive.sha256(second));
        assertThat(archive.sha256(first)).hasSize(64);
        assertThat(SkillFetcher.readSkillMarkdown(first)).contains("name: demo");
    }

    @Test
    void discoversRootOrImmediateSubdirectories(@TempDir Path dir) throws Exception {
        Path rootSkill = Files.createDirectories(dir.resolve("single"));
        Files.writeString(rootSkill.resolve("SKILL.md"), "x", StandardCharsets.UTF_8);
        assertThat(fetcher.discoverSkillDirs(rootSkill)).containsExactly(rootSkill);

        Path multi = Files.createDirectories(dir.resolve("multi"));
        Path a = Files.createDirectories(multi.resolve("a"));
        Path b = Files.createDirectories(multi.resolve("b"));
        Files.writeString(a.resolve("SKILL.md"), "x", StandardCharsets.UTF_8);
        Files.writeString(b.resolve("SKILL.md"), "x", StandardCharsets.UTF_8);
        Files.createDirectories(multi.resolve("not-a-skill"));
        assertThat(fetcher.discoverSkillDirs(multi)).containsExactly(a, b);
    }

    @Test
    void rejectsZipSlip(@TempDir Path dir) throws Exception {
        byte[] zip = zipOf("../escape.txt", "x");
        assertThatThrownBy(() -> fetcher.extractZip(zip, dir))
                .isInstanceOf(ServiceException.class)
                .hasMessageContaining("越界");
    }

    @Test
    void rejectsTooManyEntries(@TempDir Path dir) throws Exception {
        var buffer = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(buffer)) {
            for (int i = 0; i <= SkillFetcher.MAX_ENTRIES; i++) {
                zip.putNextEntry(new ZipEntry("f" + i + ".txt"));
                zip.write('x');
                zip.closeEntry();
            }
        }
        assertThatThrownBy(() -> fetcher.extractZip(buffer.toByteArray(), dir))
                .isInstanceOf(ServiceException.class)
                .hasMessageContaining("文件数上限");
    }

    @Test
    void rejectsOversizedUpload(@TempDir Path dir) {
        byte[] huge = new byte[(int) SkillFetcher.MAX_BYTES + 1];
        assertThatThrownBy(() -> fetcher.extractZip(huge, dir))
                .isInstanceOf(ServiceException.class)
                .hasMessageContaining("大小上限");
    }

    @Test
    void extractsValidZipAndListsFiles(@TempDir Path dir) throws Exception {
        byte[] zip = zipOf("SKILL.md", "---\nname: demo\ndescription: x\n---\nbody");
        Path root = fetcher.extractZip(zip, dir);
        assertThat(Files.readString(root.resolve("SKILL.md"))).contains("name: demo");
        assertThat(fetcher.discoverSkillDirs(root)).containsExactly(root);
    }

    private byte[] zipOf(String name, String content) throws Exception {
        var buffer = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(buffer)) {
            zip.putNextEntry(new ZipEntry(name));
            zip.write(content.getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }
        return buffer.toByteArray();
    }
}
