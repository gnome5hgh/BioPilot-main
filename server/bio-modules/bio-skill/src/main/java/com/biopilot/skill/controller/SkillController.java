package com.biopilot.skill.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.skill.dto.InspectResult;
import com.biopilot.skill.service.SkillService;
import java.io.IOException;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/**
 * 用户技能中心端点：列表、预览、安装、启停、更新、卸载。
 *
 * <p>归属只认登录态：所有读写都由租户插件限定在本人行；不接收客户端传来的用户标识。
 * 内置技能随仓库分发、不在本接口出现。</p>
 */
@RestController
@RequestMapping("/api/v1/skill")
public class SkillController {

    private final SkillService service;

    public SkillController(SkillService service) {
        this.service = service;
    }

    @GetMapping
    public Map<String, Object> list() {
        return Map.of("skills", service.list(uid()));
    }

    @GetMapping("/{name}")
    public Map<String, Object> detail(@PathVariable String name) {
        return Map.of("skill", service.detail(uid(), name));
    }

    /** git 来源预览：只拉取到暂存目录并解析，不写库、不写 OSS。 */
    @PostMapping("/inspect")
    public Map<String, Object> inspect(@RequestBody Map<String, Object> body) {
        String source = String.valueOf(body.getOrDefault("source", "")).trim();
        Object ref = body.get("ref");
        InspectResult result = service.inspectGit(uid(), source,
                ref == null ? null : String.valueOf(ref));
        return result(result);
    }

    /** zip 上传预览：同一套准入，只是来源换成上传字节。 */
    @PostMapping(value = "/inspect/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, Object> upload(@RequestPart("file") MultipartFile file) {
        try {
            return result(service.inspectZip(uid(), file.getBytes()));
        } catch (IOException e) {
            throw new ServiceException(422, "读取上传文件失败: " + e.getMessage());
        }
    }

    /** 确认安装：从预览暂存目录落盘（对象先落、行后写）。 */
    @PostMapping("/install")
    public Map<String, Object> install(@RequestBody Map<String, Object> body) {
        String stagingId = String.valueOf(body.getOrDefault("stagingId", "")).trim();
        return Map.of("skills", service.install(uid(), stagingId));
    }

    @PostMapping("/{name}/toggle")
    public Map<String, Object> toggle(@PathVariable String name,
                                      @RequestBody Map<String, Object> body) {
        boolean enabled = !Boolean.FALSE.equals(body.get("enabled"));
        return Map.of("skill", service.toggle(uid(), name, enabled));
    }

    /** 仅 git 来源：按记录地址重拉并原子替换。 */
    @PostMapping("/{name}/update")
    public Map<String, Object> update(@PathVariable String name) {
        return Map.of("skill", service.update(uid(), name));
    }

    @DeleteMapping("/{name}")
    public Map<String, Object> delete(@PathVariable String name) {
        service.delete(uid(), name);
        return Map.of("status", "ok");
    }

    private Map<String, Object> result(InspectResult result) {
        return Map.of("stagingId", result.stagingId(), "skills", result.skills());
    }

    private long uid() {
        return StpUtil.getLoginIdAsLong();
    }
}
