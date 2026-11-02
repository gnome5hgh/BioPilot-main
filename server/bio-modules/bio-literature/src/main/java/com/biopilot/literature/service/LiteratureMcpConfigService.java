package com.biopilot.literature.service;

import com.biopilot.common.mcp.McpServerConfig;
import com.biopilot.common.mcp.McpServerStatus;
import com.biopilot.literature.dto.LiteratureMcpServerRequest;
import com.biopilot.literature.dto.LiteratureMcpServerView;
import java.util.List;

/** MCP 检索源配置：CRUD、试连与热重连。 */
public interface LiteratureMcpConfigService {

    /** 启动时装载已启用的检索源（异步连接，失败只标记 unhealthy）。 */
    void init();

    /** 管理端清单（密钥只回显「是否配置」）。 */
    List<LiteratureMcpServerView> list();

    /** 新增检索源。 */
    LiteratureMcpServerView create(LiteratureMcpServerRequest request);

    /** 修改检索源（留空表示保持原密钥）。 */
    LiteratureMcpServerView update(String id, LiteratureMcpServerRequest request);

    /** 删除检索源。 */
    void delete(String id);

    /** 试连一次并返回连接状态。 */
    McpServerStatus test(String id);

    /** 已启用源的连接配置（供 provider 使用）。 */
    List<McpServerConfig> enabledConfigs();

    /** 声明 adapter=paper_search 的源（进入文献检索）。 */
    List<McpServerConfig> paperSearchConfigs();

    /** 配置变更后异步热重连。 */
    void reload();
}
