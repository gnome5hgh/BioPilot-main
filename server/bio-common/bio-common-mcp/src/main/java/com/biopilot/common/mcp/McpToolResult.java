package com.biopilot.common.mcp;

/**
 * 一次 MCP 工具调用的结果。
 *
 * @param structured 结构化结果（工具返回对象时由 SDK 填入；否则为 null）
 * @param text       文本结果拼合（结构化结果缺失时用于兜底）
 * @param error      工具自身是否报告错误
 */
public record McpToolResult(Object structured, String text, boolean error) {
}
