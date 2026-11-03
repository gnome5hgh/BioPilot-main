package com.biopilot.gateway.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.file.service.PaperService;
import com.biopilot.gateway.web.AgentRelay;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PutMapping;

/**
 * 引擎运行时透传：模型选择、平台设置、技能商店、终端开关、知识库试检索/重建/分块。
 *
 * <p>这些数据的真相都在 Python 引擎，Java 不做业务判断；只有分块读取前的论文
 * 归属校验留在平台侧（引擎按 id 读 RAG 索引，不再查 bio_paper）。</p>
 */
@RestController
@RequestMapping("/api/v1")
public class EngineProxyController {

    private final AgentRelay relay;
    private final PaperService papers;

    public EngineProxyController(AgentRelay relay, PaperService papers) {
        this.relay = relay;
        this.papers = papers;
    }

    /** 会话级多模型：清单（不含 key）与选择切换，切换下一 run 生效。 */
    @GetMapping("/models")
    public ResponseEntity<String> modelsList() {
        return relay.get("/models");
    }

    @PutMapping("/models/selection")
    public ResponseEntity<String> modelsSelect(@RequestBody String body) {
        return relay.post("/models/select", body);
    }

    /** 知识库分块读取：先校验论文归属，再交给引擎按 id 取块。 */
    @GetMapping("/kb/papers/{paperId}/chunks")
    public ResponseEntity<String> kbPaperChunks(@PathVariable String paperId) {
        papers.get(StpUtil.getLoginIdAsLong(), paperId);
        return relay.get("/kb/papers/" + paperId + "/chunks");
    }

    /** 强制重建：状态复位由引擎经 /internal/kb/requeue-all 回到平台侧落库。 */
    @PostMapping("/kb/reindex")
    public ResponseEntity<String> kbReindex(
            @RequestParam(defaultValue = "false") boolean force) {
        return relay.post("/kb/reindex?force=" + force, "{}");
    }

    /** 试检索：返回引擎真实检索结果，不落平台表。 */
    @PostMapping("/kb/search")
    public ResponseEntity<String> kbSearch(@RequestBody String body) {
        return relay.post("/kb/search", body);
    }

    /** 终端面板：部署开关与重启（WS 本体由 TerminalRelayHandler 单独转发）。 */
    @GetMapping("/terminal/config")
    public ResponseEntity<String> terminalConfig() {
        return relay.get("/terminal/config");
    }

    @PostMapping("/terminal/restart")
    public ResponseEntity<String> terminalRestart() {
        return relay.post("/terminal/restart", "{}");
    }

    /** 设置读/写（ADMIN 专属）：字段描述、有效值、补丁、历史与回滚。 */
    @SaCheckRole("ADMIN")
    @GetMapping("/admin/settings")
    public ResponseEntity<String> settingsGet() {
        return relay.get("/settings");
    }

    @SaCheckRole("ADMIN")
    @GetMapping("/admin/settings/history")
    public ResponseEntity<String> settingsHistory(
            @RequestParam(defaultValue = "20") int limit) {
        return relay.get("/settings/history?limit=" + limit);
    }

    @SaCheckRole("ADMIN")
    @PostMapping("/admin/settings/rollback")
    public ResponseEntity<String> settingsRollback(@RequestBody String body) {
        return relay.post("/settings/rollback", body);
    }

    @SaCheckRole("ADMIN")
    @PatchMapping("/admin/settings")
    public ResponseEntity<String> settingsSet(@RequestBody String body) {
        return relay.post("/settings", body);
    }

    /** 技能管理已迁至 bio-skill（Java 直管 bio_skill 表与 OSS），适配层不再暴露技能端点。 */
}
