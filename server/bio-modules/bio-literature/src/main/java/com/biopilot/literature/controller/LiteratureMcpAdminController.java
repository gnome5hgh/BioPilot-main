package com.biopilot.literature.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.biopilot.common.core.R;
import com.biopilot.common.mcp.McpClientManager;
import com.biopilot.common.mcp.McpServerStatus;
import com.biopilot.literature.dto.LiteratureMcpServerRequest;
import com.biopilot.literature.dto.LiteratureMcpServerView;
import com.biopilot.literature.service.LiteratureMcpConfigService;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 文献检索源管理（ADMIN）：维护 MCP server 配置、测试连通性、查看连接状态。
 *
 * <p>配置是全局的，路径挂在 {@code /agent/admin/mcp-servers}，整类要求 ADMIN 角色。
 * 密钥字段不回显，编辑时留空表示保持原值。</p>
 */
@RestController
@RequestMapping("/agent/admin/mcp-servers")
@SaCheckRole("ADMIN")
public class LiteratureMcpAdminController {

    private final LiteratureMcpConfigService configs;
    private final McpClientManager manager;

    public LiteratureMcpAdminController(LiteratureMcpConfigService configs,
                                        McpClientManager manager) {
        this.configs = configs;
        this.manager = manager;
    }

    /** 列出全部检索源配置。 */
    @GetMapping
    public R<List<LiteratureMcpServerView>> list() {
        return R.ok(configs.list());
    }

    /** 新增检索源。 */
    @PostMapping
    public R<LiteratureMcpServerView> create(@RequestBody LiteratureMcpServerRequest request) {
        return R.ok(configs.create(request));
    }

    /** 修改检索源。 */
    @PutMapping("/{id}")
    public R<LiteratureMcpServerView> update(@PathVariable String id,
                                             @RequestBody LiteratureMcpServerRequest request) {
        return R.ok(configs.update(id, request));
    }

    /** 删除检索源并断开连接。 */
    @DeleteMapping("/{id}")
    public R<Void> delete(@PathVariable String id) {
        configs.delete(id);
        return R.ok();
    }

    /** 测试一个已保存配置的连通性。 */
    @PostMapping("/{id}/test")
    public R<McpServerStatus> test(@PathVariable String id) {
        return R.ok(configs.test(id));
    }

    /** 当前连接状态（按 server 名）。 */
    @GetMapping("/status")
    public R<Map<String, McpServerStatus>> status() {
        return R.ok(manager.statuses());
    }
}
