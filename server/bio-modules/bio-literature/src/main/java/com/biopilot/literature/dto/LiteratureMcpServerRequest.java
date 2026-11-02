package com.biopilot.literature.dto;

import java.util.List;
import java.util.Map;

/**
 * 管理端新增/修改 MCP server 的请求体。
 *
 * <p>{@code env} / {@code headers} 为 null 表示保持原值（编辑时不回填密钥），
 * 空 Map 表示清空。</p>
 *
 * @param name            名称
 * @param transport       stdio / http
 * @param url             http 端点
 * @param command         stdio 可执行文件
 * @param args            stdio 参数
 * @param env             stdio 环境变量
 * @param headers         http 请求头
 * @param adapter         业务适配器（paper_search）
 * @param allowedTools    工具白名单
 * @param disabledTools   工具黑名单
 * @param enabled         是否启用
 * @param connectTimeoutMs 建连超时
 * @param callTimeoutMs    调用超时
 */
public record LiteratureMcpServerRequest(
        String name,
        String transport,
        String url,
        String command,
        List<String> args,
        Map<String, String> env,
        Map<String, String> headers,
        String adapter,
        List<String> allowedTools,
        List<String> disabledTools,
        Boolean enabled,
        Integer connectTimeoutMs,
        Integer callTimeoutMs) {
}
