package com.biopilot.skill.support;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.skill.dto.SkillInfo;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 标准形态包准入：字段校验、资源清单与 tools.py 拒绝。 */
class SkillPackageValidatorTest {

    private final SkillPackageValidator validator = new SkillPackageValidator();

    @Test
    void acceptsStandardPackage(@TempDir Path dir) throws Exception {
        Path skill = Files.createDirectories(dir.resolve("demo-skill"));
        Files.writeString(skill.resolve("SKILL.md"), """
                ---
                name: demo-skill
                description: 演示流程，用于测试。
                license: MIT
                metadata:
                  version: "1.2.0"
                ---
                正文
                """, StandardCharsets.UTF_8);
        Files.createDirectories(skill.resolve("references"));
        Files.writeString(skill.resolve("references/fmt.md"), "格式卡", StandardCharsets.UTF_8);

        SkillInfo info = validator.inspect(skill);

        assertThat(info.name()).isEqualTo("demo-skill");
        assertThat(info.description()).contains("演示流程");
        assertThat(info.version()).isEqualTo("1.2.0");
        assertThat(info.license()).isEqualTo("MIT");
        assertThat(info.resources()).containsExactly("references/fmt.md");
    }

    @Test
    void rejectsMissingName(@TempDir Path dir) throws Exception {
        Path skill = Files.createDirectories(dir.resolve("broken"));
        Files.writeString(skill.resolve("SKILL.md"), "---\ndescription: x\n---\nbody",
                StandardCharsets.UTF_8);
        assertThatThrownBy(() -> validator.inspect(skill))
                .isInstanceOf(ServiceException.class)
                .hasMessageContaining("name");
    }

    @Test
    void rejectsInvalidName(@TempDir Path dir) throws Exception {
        Path skill = Files.createDirectories(dir.resolve("Bad_Name"));
        Files.writeString(skill.resolve("SKILL.md"),
                "---\nname: Bad_Name\ndescription: x\n---\nbody", StandardCharsets.UTF_8);
        assertThatThrownBy(() -> validator.inspect(skill))
                .isInstanceOf(ServiceException.class)
                .hasMessageContaining("name 非法");
    }

    @Test
    void rejectsMissingDescription(@TempDir Path dir) throws Exception {
        Path skill = Files.createDirectories(dir.resolve("no-desc"));
        Files.writeString(skill.resolve("SKILL.md"), "---\nname: no-desc\n---\nbody",
                StandardCharsets.UTF_8);
        assertThatThrownBy(() -> validator.inspect(skill))
                .isInstanceOf(ServiceException.class)
                .hasMessageContaining("description");
    }

    @Test
    void rejectsToolsPy(@TempDir Path dir) throws Exception {
        Path skill = Files.createDirectories(dir.resolve("with-code"));
        Files.writeString(skill.resolve("SKILL.md"),
                "---\nname: with-code\ndescription: x\n---\nbody", StandardCharsets.UTF_8);
        Files.writeString(skill.resolve("tools.py"), "TOOLS = []", StandardCharsets.UTF_8);
        assertThatThrownBy(() -> validator.inspect(skill))
                .isInstanceOf(ServiceException.class)
                .hasMessageContaining("tools.py");
    }

    @Test
    void allowsStandardScriptsDirectory(@TempDir Path dir) throws Exception {
        Path skill = Files.createDirectories(dir.resolve("with-scripts"));
        Files.writeString(skill.resolve("SKILL.md"),
                "---\nname: with-scripts\ndescription: x\n---\nbody", StandardCharsets.UTF_8);
        Files.createDirectories(skill.resolve("scripts"));
        Files.writeString(skill.resolve("scripts/run.sh"), "echo hi", StandardCharsets.UTF_8);
        SkillInfo info = validator.inspect(skill);
        assertThat(info.resources()).containsExactly("scripts/run.sh");
    }

    @Test
    void rejectsSymlinks(@TempDir Path dir) throws Exception {
        Path skill = Files.createDirectories(dir.resolve("with-link"));
        Files.writeString(skill.resolve("SKILL.md"),
                "---\nname: with-link\ndescription: x\n---\nbody", StandardCharsets.UTF_8);
        Path outside = Files.writeString(dir.resolve("outside.txt"), "secret",
                StandardCharsets.UTF_8);
        try {
            Files.createSymbolicLink(skill.resolve("link.txt"), outside);
        } catch (UnsupportedOperationException | java.io.IOException e) {
            return; // 文件系统不支持符号链接：跳过该断言
        }
        assertThatThrownBy(() -> validator.inspect(skill))
                .isInstanceOf(ServiceException.class)
                .hasMessageContaining("符号链接");
    }
}
