package com.biopilot.literature.service.impl;

import com.biopilot.literature.service.LiteratureMcpConfigService;

import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.mcp.McpClientManager;
import com.biopilot.common.mcp.McpServerConfig;
import com.biopilot.common.mcp.McpServerStatus;
import com.biopilot.literature.domain.LiteratureMcpServer;
import com.biopilot.literature.dto.LiteratureMcpServerRequest;
import com.biopilot.literature.dto.LiteratureMcpServerView;
import com.biopilot.literature.mapper.LiteratureMcpServerMapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;

/**
 * 文献检索 MCP server 的管理员配置：落库、脱敏展示、连通性测试与热重连。
 *
 * <p>配置是全局的（无 user_id），由 ADMIN 维护；连接生命周期交给
 * {@link McpClientManager}。启动时异步连接，单个 server 失败只影响它自己，不阻塞
 * 平台启动；任何增删改都触发一次异步重连。</p>
 */
@Service
public class LiteratureMcpConfigServiceImpl implements LiteratureMcpConfigService {

    private static final Logger log = LoggerFactory.getLogger(LiteratureMcpConfigService.class);
    private static final String PAPER_SEARCH_ADAPTER = "paper_search";
    private static final int DEFAULT_CONNECT_MS = 30_000;
    private static final int DEFAULT_CALL_MS = 60_000;

    private final LiteratureMcpServerMapper mapper;
    private final McpClientManager manager;
    private final ObjectMapper json;

    /** 首次部署时默认检索源地址：本机开发指向映射端口，compose 内由环境变量改成服务名。 */
    @Value("${biopilot.paper-search.url:http://127.0.0.1:8000/mcp}")
    private String defaultPaperSearchUrl;

    /** 是否在空库时自动种入默认检索源；关掉后完全由管理员手工配置。 */
    @Value("${biopilot.paper-search.enabled:true}")
    private boolean defaultPaperSearchEnabled;

    public LiteratureMcpConfigServiceImpl(LiteratureMcpServerMapper mapper,
                                      McpClientManager manager,
                                      ObjectMapper json) {
        this.mapper = mapper;
        this.manager = manager;
        this.json = json;
    }

    /** 空库时种入默认 paper-search 源，然后异步连接已启用的 server；失败只记日志。 */
    @PostConstruct
    public void init() {
        try {
            if (defaultPaperSearchEnabled && mapper.selectCount(null) == 0) {
                LiteratureMcpServer entity = new LiteratureMcpServer();
                entity.setId("paper-search");
                entity.setName("paper-search");
                entity.setTransport("http");
                entity.setUrl(defaultPaperSearchUrl);
                entity.setAdapter(PAPER_SEARCH_ADAPTER);
                entity.setAllowedToolsJson("[\"search_papers\"]");
                entity.setEnabled(1);
                entity.setConnectTimeoutMs(DEFAULT_CONNECT_MS);
                entity.setCallTimeoutMs(DEFAULT_CALL_MS);
                entity.setCreatedAt(Instant.now().toString());
                entity.setUpdatedAt(Instant.now().toString());
                mapper.insert(entity);
                log.info("已种入默认 MCP 检索源 paper-search（{}）", defaultPaperSearchUrl);
            }
            reload();
        } catch (Exception e) {
            log.warn("MCP 配置初始化失败（平台继续启动）: {}", e.getMessage());
        }
    }

    /** 读取全部配置（密钥字段只回显「是否配置」）。 */
    public List<LiteratureMcpServerView> list() {
        return mapper.selectList(null).stream()
                .sorted((a, b) -> a.getName().compareToIgnoreCase(b.getName()))
                .map(this::toView)
                .toList();
    }

    /** 新增配置并触发热重连。 */
    public LiteratureMcpServerView create(LiteratureMcpServerRequest request) {
        LiteratureMcpServer entity = new LiteratureMcpServer();
        entity.setId(UUID.randomUUID().toString().replace("-", ""));
        entity.setCreatedAt(Instant.now().toString());
        apply(entity, request, false);
        try {
            mapper.insert(entity);
        } catch (DuplicateKeyException e) {
            throw new ServiceException(409, "MCP server 名称已存在：" + entity.getName());
        }
        reload();
        return toView(entity);
    }

    /** 修改配置；env/headers 为 null 时保留原值，空 Map 表示清空。 */
    public LiteratureMcpServerView update(String id, LiteratureMcpServerRequest request) {
        LiteratureMcpServer entity = mapper.selectById(id);
        if (entity == null) {
            throw new ServiceException(404, "MCP server 不存在：" + id);
        }
        apply(entity, request, true);
        try {
            mapper.updateById(entity);
        } catch (DuplicateKeyException e) {
            throw new ServiceException(409, "MCP server 名称已存在：" + entity.getName());
        }
        reload();
        return toView(entity);
    }

    /** 删除配置并断开连接。 */
    public void delete(String id) {
        LiteratureMcpServer entity = mapper.selectById(id);
        if (entity == null) {
            throw new ServiceException(404, "MCP server 不存在：" + id);
        }
        mapper.deleteById(id);
        manager.disconnect(entity.getName());
    }

    /** 测试一个已保存配置的连通性；不替换线上连接。 */
    public McpServerStatus test(String id) {
        LiteratureMcpServer entity = mapper.selectById(id);
        if (entity == null) {
            throw new ServiceException(404, "MCP server 不存在：" + id);
        }
        return manager.probe(toConfig(entity));
    }

    /** 当前所有已启用配置（供管理端状态展示与通用重连）。 */
    public List<McpServerConfig> enabledConfigs() {
        return mapper.selectList(null).stream()
                .filter(e -> enabled(e))
                .map(this::toConfig)
                .toList();
    }

    /** 文献检索可用的 provider 配置：启用且声明为 paper_search 适配器。 */
    public List<McpServerConfig> paperSearchConfigs() {
        return mapper.selectList(null).stream()
                .filter(e -> enabled(e))
                .filter(e -> PAPER_SEARCH_ADAPTER.equalsIgnoreCase(e.getAdapter()))
                .map(this::toConfig)
                .toList();
    }

    /** 触发一次异步重连；不在请求路径里等待子进程。 */
    public void reload() {
        manager.reloadAsync(enabledConfigs());
    }

    private void apply(LiteratureMcpServer entity, LiteratureMcpServerRequest request,
                       boolean updating) {
        if (request == null) {
            throw new ServiceException(422, "配置不能为空");
        }
        String name = trim(request.name());
        if (name.isBlank() || !name.matches("[a-zA-Z0-9_-]{1,64}")) {
            throw new ServiceException(422, "MCP server 名非法（字母/数字/下划线/连字符，1-64 位）");
        }
        String transport = trim(request.transport()).isBlank()
                ? "http" : trim(request.transport()).toLowerCase();
        if (!transport.equals("http") && !transport.equals("stdio")) {
            throw new ServiceException(422, "transport 只能是 http 或 stdio");
        }
        String url = trim(request.url());
        String command = trim(request.command());
        if (transport.equals("http") && !url.startsWith("http://") && !url.startsWith("https://")) {
            throw new ServiceException(422, "http 传输必须提供 http(s) 端点");
        }
        if (transport.equals("stdio") && command.isBlank()) {
            throw new ServiceException(422, "stdio 传输必须提供 command");
        }
        entity.setName(name);
        entity.setTransport(transport);
        entity.setUrl(url);
        entity.setCommand(command);
        // 编辑时前端不展示 args：null 保持原值（stdio 的启动参数不能因改名称被清掉）
        if (!updating || request.args() != null) {
            entity.setArgsJson(writeJson(request.args()));
        }
        entity.setAdapter(trim(request.adapter()).isBlank()
                ? PAPER_SEARCH_ADAPTER : trim(request.adapter()));
        entity.setAllowedToolsJson(writeJson(request.allowedTools()));
        entity.setDisabledToolsJson(writeJson(request.disabledTools()));
        entity.setEnabled(Boolean.FALSE.equals(request.enabled()) ? 0 : 1);
        entity.setConnectTimeoutMs(positive(request.connectTimeoutMs(), DEFAULT_CONNECT_MS));
        entity.setCallTimeoutMs(positive(request.callTimeoutMs(), DEFAULT_CALL_MS));
        // 编辑时前端不回填密钥：null 保持原值，空 Map 才清空
        if (!updating || request.env() != null) {
            entity.setEnvJson(writeJson(request.env()));
        }
        if (!updating || request.headers() != null) {
            entity.setHeadersJson(writeJson(request.headers()));
        }
        entity.setUpdatedAt(Instant.now().toString());
    }

    private LiteratureMcpServerView toView(LiteratureMcpServer entity) {
        return new LiteratureMcpServerView(
                entity.getId(),
                entity.getName(),
                entity.getTransport(),
                entity.getUrl(),
                entity.getCommand(),
                readStringList(entity.getArgsJson()),
                !readStringMap(entity.getEnvJson()).isEmpty(),
                !readStringMap(entity.getHeadersJson()).isEmpty(),
                entity.getAdapter(),
                readStringList(entity.getAllowedToolsJson()),
                readStringList(entity.getDisabledToolsJson()),
                enabled(entity),
                intOr(entity.getConnectTimeoutMs(), DEFAULT_CONNECT_MS),
                intOr(entity.getCallTimeoutMs(), DEFAULT_CALL_MS));
    }

    private McpServerConfig toConfig(LiteratureMcpServer entity) {
        return new McpServerConfig(
                entity.getName(),
                entity.getTransport(),
                entity.getUrl(),
                entity.getCommand(),
                readStringList(entity.getArgsJson()),
                readStringMap(entity.getEnvJson()),
                readStringMap(entity.getHeadersJson()),
                enabled(entity),
                Duration.ofMillis(intOr(entity.getConnectTimeoutMs(), DEFAULT_CONNECT_MS)),
                Duration.ofMillis(intOr(entity.getCallTimeoutMs(), DEFAULT_CALL_MS)),
                readStringList(entity.getAllowedToolsJson()),
                readStringList(entity.getDisabledToolsJson()));
    }

    private String writeJson(Object value) {
        if (value == null) {
            return null;
        }
        try {
            return json.writeValueAsString(value);
        } catch (Exception e) {
            throw new ServiceException(422, "配置序列化失败：" + e.getMessage());
        }
    }

    private List<String> readStringList(String raw) {
        if (raw == null || raw.isBlank()) {
            return List.of();
        }
        try {
            List<String> values = json.readValue(raw, new TypeReference<List<String>>() {
            });
            return values == null ? List.of() : new ArrayList<>(values);
        } catch (Exception e) {
            log.warn("MCP 配置 JSON 解析失败（按空列表处理）: {}", e.getMessage());
            return List.of();
        }
    }

    private Map<String, String> readStringMap(String raw) {
        if (raw == null || raw.isBlank()) {
            return Map.of();
        }
        try {
            Map<String, String> values = json.readValue(raw,
                    new TypeReference<Map<String, String>>() {
                    });
            return values == null ? Map.of() : values;
        } catch (Exception e) {
            log.warn("MCP 配置 JSON 解析失败（按空表处理）: {}", e.getMessage());
            return Map.of();
        }
    }

    private static boolean enabled(LiteratureMcpServer entity) {
        return entity.getEnabled() == null || entity.getEnabled() != 0;
    }

    private static String trim(String value) {
        return value == null ? "" : value.trim();
    }

    private static int positive(Integer value, int fallback) {
        return value == null || value <= 0 ? fallback : value;
    }

    private static int intOr(Integer value, int fallback) {
        return value == null ? fallback : value;
    }
}
