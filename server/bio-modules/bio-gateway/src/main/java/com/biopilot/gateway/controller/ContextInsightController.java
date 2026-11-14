package com.biopilot.gateway.controller;

import com.biopilot.common.core.R;
import com.biopilot.skill.dto.SkillView;
import com.biopilot.skill.service.SkillService;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 上下文侧栏（读侧）：查库组装上下文时间线与窗口组成明细，供对话页侧栏回显。
 *
 * 平台读侧功能，引擎不提供服务端点：引擎落盘表（bio_message / bio_agent_state /
 * bio_memory_block，均为「Python 写、Java 只读」）直读，与 SessionController 的会话
 * 列表同一模式；技能清单经 bio-skill 公开接口（{@link SkillService#list}）取得。
 * token 数值一律取引擎已算好的落盘值（meta.usage 与存量用量端点），Java
 * 侧不做 token 估算（不复制引擎口径）。
 *
 * 跨栈只读契约（引擎侧变更需同步本类，已登记 bio-gateway/AGENTS.md）：
 * <ul>
 *   <li>bio_message.meta 的 usage{prompt_tokens, completion_tokens, cached_tokens,
 *       reasoning_tokens} 与 model 字段——响应信封落盘格式；</li>
 *   <li>压缩摘要消息的固定开场白前缀 {@link #SUMMARY_PREFIX}；</li>
 *   <li>bio_agent_state.message_ids——当前 in-context 窗口的消息 id 清单，
 *       压缩后同步收缩。</li>
 * </ul>
 * 浏览器只返回三类可展示原文的类目：技能清单（bio-skill 公开接口的当前启用清单）、
 * 记忆块、窗口内消息。系统提示词/可派发清单/意图/工具定义四类的原文只在引擎进程内组装，
 * 平台侧无既有端点、落库即副本（违反单一落点），已从浏览器移除。时间线响应的 seq
 * 是 1 起始的请求展示序号（按消息落盘序编号），不是数据库 seq 列。
 */
@RestController
@RequestMapping("/api/v1/conversations")
public class ContextInsightController {

    /** 压缩摘要消息（UserMessage）的固定开场白前缀；用于标记压缩点位置。 */
    static final String SUMMARY_PREFIX =
            "This session is being continued from a previous conversation that ran out of context.";

    /** 输入骤降阈值：prompt 比上一报用量请求低两成以上视为压缩点（窗口收缩是唯一让输入变小的因素）。 */
    private static final double DROP_RATIO = 0.8;

    private final JdbcTemplate jdbc;
    private final SkillService skillService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public ContextInsightController(JdbcTemplate jdbc, SkillService skillService) {
        this.jdbc = jdbc;
        this.skillService = skillService;
    }

    /**
     * 上下文时间线：从 assistant 消息的信封重建逐请求用量序列（含压缩点标记）。
     * 压缩永不删 SQL 行，序列天然完整；端点未报用量的请求 token 四项为 null。
     */
    @GetMapping("/{conversationId}/context-timeline")
    public R<Map<String, Object>> timeline(@PathVariable String conversationId) {
        String userId = currentUserId();
        if (isBlank(conversationId)) {
            return R.ok(Map.of("requests", List.of()));
        }
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT seq, meta, created_at FROM bio_message"
                        + " WHERE agent_id=? AND user_id=? AND role='assistant' AND meta IS NOT NULL"
                        + " ORDER BY seq",
                conversationId, userId);
        List<Integer> summarySeqs = jdbc.queryForList(
                "SELECT seq FROM bio_message"
                        + " WHERE agent_id=? AND user_id=? AND role='user' AND content LIKE ?"
                        + " ORDER BY seq",
                Integer.class, conversationId, userId, SUMMARY_PREFIX + "%");

        List<Map<String, Object>> requests = new ArrayList<>();
        long prevPrompt = -1;
        long prevSeq = 0;
        int index = 1;
        for (Map<String, Object> row : rows) {
            JsonNode meta = parseMeta((String) row.get("meta"));
            JsonNode usage = meta.path("usage");
            Long prompt = optionalLong(usage, "prompt_tokens");
            // 压缩点两信号取或：输入骤降；上一请求之后紧邻摘要消息（覆盖端点未报用量的场景）
            boolean dropped = prompt != null && prevPrompt >= 0
                    && prompt < (long) (prevPrompt * DROP_RATIO);
            boolean summarized = false;
            for (Integer summarySeq : summarySeqs) {
                if (summarySeq > prevSeq && summarySeq <= ((Number) row.get("seq")).longValue()) {
                    summarized = true;
                    break;
                }
            }
            Map<String, Object> point = new LinkedHashMap<>();
            point.put("seq", index);
            point.put("prompt_tokens", prompt);
            point.put("completion_tokens", optionalLong(usage, "completion_tokens"));
            point.put("cached_tokens", optionalLong(usage, "cached_tokens"));
            point.put("reasoning_tokens", optionalLong(usage, "reasoning_tokens"));
            point.put("model", textOrNull(meta, "model"));
            point.put("created_at", row.get("created_at"));
            point.put("compacted", dropped || summarized);
            requests.add(point);
            if (prompt != null) {
                prevPrompt = prompt;
            }
            prevSeq = ((Number) row.get("seq")).longValue();
            index++;
        }
        return R.ok(Map.of("requests", requests));
    }

    /**
     * 窗口组成明细：为上下文浏览器组装可展开原文。技能清单/窗口内消息/记忆块
     * 三类分别来自 bio-skill 公开接口与引擎落盘表（bio_message / bio_memory_block）；
     * 系统提示词/可派发清单/意图/工具定义四类原文只在引擎进程内组装，无数据库落点，
     * 已从浏览器移除。会话从未运行过（无 agent_state 行）时返回 null，前端显示空态。
     */
    @GetMapping("/{conversationId}/context-composition")
    public R<Map<String, Object>> composition(@PathVariable String conversationId) {
        String userId = currentUserId();
        if (isBlank(conversationId)) {
            return R.ok(emptyComposition());
        }
        List<Map<String, Object>> states = jdbc.queryForList(
                "SELECT context_window_limit, message_ids FROM bio_agent_state"
                        + " WHERE agent_id=? AND user_id=?",
                conversationId, userId);
        if (states.isEmpty()) {
            return R.ok(emptyComposition());
        }
        Map<String, Object> state = states.get(0);

        // 窗口内消息：按 message_ids 顺序还原（压缩后窗口外的行自然缺席）
        List<Map<String, Object>> messageItems = new ArrayList<>();
        List<String> windowIds = parseIdList((String) state.get("message_ids"));
        if (!windowIds.isEmpty()) {
            List<Object> params = new ArrayList<>(windowIds);
            params.add(conversationId);
            params.add(userId);
            String placeholders = String.join(",", java.util.Collections.nCopies(windowIds.size(), "?"));
            List<Map<String, Object>> rows = jdbc.queryForList(
                    "SELECT id, role, content, tool_calls FROM bio_message"
                            + " WHERE id IN (" + placeholders + ") AND agent_id=? AND user_id=?",
                    params.toArray());
            Map<String, Map<String, Object>> byId = new HashMap<>();
            for (Map<String, Object> row : rows) {
                byId.put((String) row.get("id"), row);
            }
            for (String id : windowIds) {
                Map<String, Object> row = byId.get(id);
                if (row == null) {
                    continue;
                }
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("label", row.get("role"));
                item.put("content", row.get("content") == null ? "" : row.get("content"));
                item.put("tool_calls", parseToolCalls((String) row.get("tool_calls")));
                messageItems.add(item);
            }
        }

        // 记忆块原文：逐块展示（引擎 Memory.compile() 的素材源）
        List<Map<String, Object>> memoryItems = new ArrayList<>();
        List<Map<String, Object>> blocks = jdbc.queryForList(
                "SELECT label, value FROM bio_memory_block WHERE user_id=? ORDER BY seq",
                userId);
        for (Map<String, Object> block : blocks) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("label", block.get("label"));
            item.put("content", block.get("value"));
            item.put("tool_calls", null);
            memoryItems.add(item);
        }

        // 技能清单：经 bio-skill 公开接口取当前用户的技能视图（行级 user_id 过滤由
        // 租户插件统一注入），过滤 enabled 展示当前启用清单（管理面状态）；非该轮
        // 注入 head 的原文，引擎的渲染与截断口径不在此复刻
        List<Map<String, Object>> skillItems = new ArrayList<>();
        for (SkillView skill : skillService.list(Long.parseLong(userId))) {
            if (!skill.enabled()) {
                continue;
            }
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("label", skill.name());
            item.put("content", skill.description());
            item.put("tool_calls", null);
            skillItems.add(item);
        }

        List<Map<String, Object>> categories = new ArrayList<>();
        categories.add(category("skills", skillItems));
        categories.add(category("memory", memoryItems));
        categories.add(category("messages", messageItems));

        Object limit = state.get("context_window_limit");
        Map<String, Object> composition = new LinkedHashMap<>();
        composition.put("mode", "db");
        composition.put("limit", limit == null ? 0 : ((Number) limit).longValue());
        composition.put("categories", categories);
        return R.ok(Map.of("composition", composition));
    }

    private Map<String, Object> category(String key, List<Map<String, Object>> items) {
        Map<String, Object> cat = new LinkedHashMap<>();
        cat.put("key", key);
        cat.put("items", items);
        return cat;
    }

    /** DB 里的 tool_calls 是 OpenAI 原始形状（function.name/arguments），展平成展示用 {name, arguments}。 */
    private List<Map<String, String>> parseToolCalls(String toolCallsJson) {
        if (toolCallsJson == null || toolCallsJson.isEmpty()) {
            return null;
        }
        try {
            JsonNode arr = objectMapper.readTree(toolCallsJson);
            List<Map<String, String>> calls = new ArrayList<>();
            for (JsonNode tc : arr) {
                JsonNode fn = tc.path("function");
                calls.add(Map.of(
                        "name", fn.path("name").asText("?"),
                        "arguments", fn.path("arguments").asText("")));
            }
            return calls;
        } catch (Exception e) {
            return null;
        }
    }

    private JsonNode parseMeta(String metaJson) {
        if (metaJson == null || metaJson.isEmpty()) {
            return objectMapper.createObjectNode();
        }
        try {
            return objectMapper.readTree(metaJson);
        } catch (Exception e) {
            return objectMapper.createObjectNode();
        }
    }

    private List<String> parseIdList(String messageIdsJson) {
        if (messageIdsJson == null || messageIdsJson.isEmpty()) {
            return List.of();
        }
        try {
            return objectMapper.readValue(messageIdsJson, new TypeReference<List<String>>() {
            });
        } catch (Exception e) {
            return List.of();
        }
    }

    private Long optionalLong(JsonNode node, String field) {
        return node.has(field) && node.get(field).isNumber() ? node.get(field).asLong() : null;
    }

    private String textOrNull(JsonNode node, String field) {
        return node.has(field) && !node.get(field).isNull() ? node.get(field).asText() : null;
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private Map<String, Object> emptyComposition() {
        // composition 显式为 null：前端以 null 判空态（Map.of 不允许 null 值，用 HashMap）
        Map<String, Object> body = new HashMap<>();
        body.put("composition", null);
        return body;
    }

    private String currentUserId() {
        return cn.dev33.satoken.stp.StpUtil.getLoginIdAsString();
    }
}
