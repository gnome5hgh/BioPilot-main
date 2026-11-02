package com.biopilot.literature.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

/**
 * 文献检索 MCP server 的管理员配置行。
 *
 * <p>这是全局配置（无 user_id），只允许 ADMIN 读写；JSON 列以字符串存储，避免为几个
 * 自由结构引入额外类型处理器。密钥类字段（env/headers）在接口层脱敏。</p>
 */
@TableName("bio_literature_mcp_server")
public class LiteratureMcpServer {

    @TableId(type = IdType.INPUT)
    private String id;
    private String name;
    private String transport;
    private String url;
    private String command;
    private String argsJson;
    private String envJson;
    private String headersJson;
    private String adapter;
    private String allowedToolsJson;
    private String disabledToolsJson;
    private Integer enabled;
    private Integer connectTimeoutMs;
    private Integer callTimeoutMs;
    private String createdAt;
    private String updatedAt;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getTransport() {
        return transport;
    }

    public void setTransport(String transport) {
        this.transport = transport;
    }

    public String getUrl() {
        return url;
    }

    public void setUrl(String url) {
        this.url = url;
    }

    public String getCommand() {
        return command;
    }

    public void setCommand(String command) {
        this.command = command;
    }

    public String getArgsJson() {
        return argsJson;
    }

    public void setArgsJson(String argsJson) {
        this.argsJson = argsJson;
    }

    public String getEnvJson() {
        return envJson;
    }

    public void setEnvJson(String envJson) {
        this.envJson = envJson;
    }

    public String getHeadersJson() {
        return headersJson;
    }

    public void setHeadersJson(String headersJson) {
        this.headersJson = headersJson;
    }

    public String getAdapter() {
        return adapter;
    }

    public void setAdapter(String adapter) {
        this.adapter = adapter;
    }

    public String getAllowedToolsJson() {
        return allowedToolsJson;
    }

    public void setAllowedToolsJson(String allowedToolsJson) {
        this.allowedToolsJson = allowedToolsJson;
    }

    public String getDisabledToolsJson() {
        return disabledToolsJson;
    }

    public void setDisabledToolsJson(String disabledToolsJson) {
        this.disabledToolsJson = disabledToolsJson;
    }

    public Integer getEnabled() {
        return enabled;
    }

    public void setEnabled(Integer enabled) {
        this.enabled = enabled;
    }

    public Integer getConnectTimeoutMs() {
        return connectTimeoutMs;
    }

    public void setConnectTimeoutMs(Integer connectTimeoutMs) {
        this.connectTimeoutMs = connectTimeoutMs;
    }

    public Integer getCallTimeoutMs() {
        return callTimeoutMs;
    }

    public void setCallTimeoutMs(Integer callTimeoutMs) {
        this.callTimeoutMs = callTimeoutMs;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }

    public String getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(String updatedAt) {
        this.updatedAt = updatedAt;
    }
}
