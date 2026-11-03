package com.biopilot.skill.support;

import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.skill.dto.SkillInfo;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import org.springframework.stereotype.Component;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;

/**
 * agentskills.io 标准形态包的准入校验。
 *
 * <p>只接受规范定义的内容：SKILL.md（必填）+ 任意资源文件。平台不扩展 skill
 * 格式——目录里出现 tools.py 直接拒绝（那是「加载即执行」的私有扩展，不是标准）。</p>
 */
@Component
public class SkillPackageValidator {

    /** 规范：1-64 字符，小写字母/数字/连字符，不以连字符开头结尾、无连续连字符。 */
    private static final Pattern NAME = Pattern.compile("^[a-z0-9]+(-[a-z0-9]+)*$");
    private static final int MAX_NAME = 64;
    private static final int MAX_DESCRIPTION = 1024;
    private static final int MAX_RESOURCES = 2000;

    /** 与 Python 的 frontmatter 解析保持同一契约：闭合围栏 + 可选空段。 */
    private static final Pattern FRONTMATTER =
            Pattern.compile("^---\\s*\\n(?:(.*?)\\n)?---\\s*\\n?(.*)", Pattern.DOTALL);

    /**
     * 校验并解析一个技能目录。
     *
     * @param dir 技能目录（含 SKILL.md）
     * @return 名称/描述/版本/license/资源清单
     * @throws ServiceException 缺少 SKILL.md、frontmatter 非法或含 tools.py（422）
     */
    public SkillInfo inspect(Path dir) {
        Path skillMd = dir.resolve("SKILL.md");
        if (!Files.isRegularFile(skillMd)) {
            throw new ServiceException(422, "缺少 SKILL.md，不是有效的技能包");
        }
        if (Files.exists(dir.resolve("tools.py"))) {
            throw new ServiceException(422,
                    "技能包含非标准文件 tools.py：平台只接受 agentskills.io 标准形态包");
        }
        rejectSymlinks(dir);
        String text;
        try {
            text = Files.readString(skillMd, StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new ServiceException(422, "读取 SKILL.md 失败: " + e.getMessage());
        }
        Map<String, Object> meta = parseFrontmatter(text);
        Object rawName = meta.get("name");
        String name = rawName == null ? "" : String.valueOf(rawName).trim();
        if (name.isEmpty()) {
            throw new ServiceException(422, "SKILL.md frontmatter 缺少必填字段 name");
        }
        if (name.length() > MAX_NAME || !NAME.matcher(name).matches()) {
            throw new ServiceException(422,
                    "name 非法（小写字母/数字/连字符，1-64 字符，不以连字符开头结尾、无连续连字符）: " + name);
        }
        Object rawDesc = meta.get("description");
        String description = rawDesc == null ? "" : String.valueOf(rawDesc).trim();
        if (description.isEmpty()) {
            throw new ServiceException(422, "SKILL.md frontmatter 缺少必填字段 description");
        }
        if (description.length() > MAX_DESCRIPTION) {
            throw new ServiceException(422, "description 超过 1024 字符上限");
        }
        String version = "";
        Object rawMeta = meta.get("metadata");
        if (rawMeta instanceof Map<?, ?> map && map.get("version") != null) {
            version = String.valueOf(map.get("version")).trim();
        }
        String license = meta.get("license") == null ? "" : String.valueOf(meta.get("license")).trim();
        return new SkillInfo(name, description, version, license, listResources(dir));
    }

    /** 解析 frontmatter；无围栏时返回空映射（与 Python parse_frontmatter 一致）。 */
    private Map<String, Object> parseFrontmatter(String text) {
        Matcher m = FRONTMATTER.matcher(text);
        if (!m.find()) {
            return Map.of();
        }
        String yaml = m.group(1) == null ? "" : m.group(1);
        Object loaded;
        try {
            loaded = new Yaml(new SafeConstructor(new LoaderOptions())).load(yaml);
        } catch (RuntimeException e) {
            throw new ServiceException(422, "SKILL.md frontmatter 不是合法 YAML: " + e.getMessage());
        }
        if (loaded == null) {
            return Map.of();
        }
        if (!(loaded instanceof Map<?, ?>)) {
            throw new ServiceException(422, "SKILL.md frontmatter 必须是键值映射");
        }
        Map<String, Object> result = new java.util.LinkedHashMap<>();
        ((Map<?, ?>) loaded).forEach((k, v) -> result.put(String.valueOf(k), v));
        return result;
    }

    /** 资源清单：SKILL.md 之外的相对路径（准入展示用）；超过上限即拒绝。 */
    private List<String> listResources(Path dir) {
        List<String> resources = new ArrayList<>();
        try (Stream<Path> walk = Files.walk(dir)) {
            walk.filter(Files::isRegularFile)
                    .filter(p -> !p.getFileName().toString().equals("SKILL.md"))
                    .map(p -> dir.relativize(p).toString().replace('\\', '/'))
                    .sorted(Comparator.naturalOrder())
                    .forEach(resources::add);
        } catch (IOException e) {
            throw new ServiceException(422, "读取技能目录失败: " + e.getMessage());
        }
        if (resources.size() > MAX_RESOURCES) {
            throw new ServiceException(422, "技能文件数超过上限 " + MAX_RESOURCES);
        }
        return resources;
    }

    /** 拒绝包内符号链接：解包/读取都不得越过技能目录。 */
    private void rejectSymlinks(Path dir) {
        try (Stream<Path> walk = Files.walk(dir)) {
            if (walk.anyMatch(Files::isSymbolicLink)) {
                throw new ServiceException(422, "技能包含符号链接，拒绝安装");
            }
        } catch (IOException e) {
            throw new ServiceException(422, "读取技能目录失败: " + e.getMessage());
        }
    }
}
