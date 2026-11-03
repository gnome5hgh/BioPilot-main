package com.biopilot.common.net;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.function.Function;

/**
 * 带逐跳校验的安全 GET 下载：重定向手动跟随、每一跳都过校验、响应体按上限流式截断。
 *
 * <p>校验真实请求链而非预解析链——HEAD 预解析与 GET 的重定向路径可能分叉（Springer/DOI
 * 即如此），预解析结果对 GET 无效。校验器通常传 {@link UrlGuard#validateExternal}；
 * 本类不限定校验语义，测试可注入更宽松的校验函数。</p>
 */
public final class SafeHttpFetcher {

    /** 单跳 HTTP 传输抽象：生产用 JDK HttpClient，测试注入假传输（不开真端口）。 */
    public interface HttpTransport {
        HttpResponse<InputStream> send(HttpRequest request) throws IOException, InterruptedException;
    }

    /** 单跳请求超时上限：总预算内每跳至多花这么久，剩余不足时按剩余计。 */
    private static final Duration MAX_REQUEST_TIMEOUT = Duration.ofSeconds(30);

    private final HttpTransport transport;
    private final long maxBytes;

    /** 生产构造：JDK HttpClient，禁自动重定向，连接超时 5 秒。 */
    public SafeHttpFetcher(long maxBytes) {
        this(maxBytes, defaultTransport());
    }

    /** 测试构造：注入假传输与响应体大小上限。 */
    public SafeHttpFetcher(long maxBytes, HttpTransport transport) {
        this.maxBytes = maxBytes;
        this.transport = transport;
    }

    /**
     * GET 下载字节。
     *
     * @param url 起始地址
     * @param validator 每跳目标校验：输入 URL 字符串，返回校验后的 URI，违规抛 IllegalArgumentException
     * @param maxRedirects 允许跟随的重定向跳数
     * @param totalBudget 含全部重定向的总时间预算；单跳超时取剩余预算与 30 秒的较小者
     * @return 响应体字节（不超过 maxBytes）
     * @throws IllegalArgumentException 校验违规，或响应超过 maxBytes
     * @throws IllegalStateException 网络失败、HTTP 4xx/5xx、重定向缺 Location、超跳数或超总预算
     */
    public byte[] fetch(String url, Function<String, URI> validator,
                        int maxRedirects, Duration totalBudget) {
        long deadline = System.nanoTime() + totalBudget.toNanos();
        URI current = validator.apply(url);
        HttpResponse<InputStream> response = null;
        int hops = 0;
        while (true) {
            response = send(request(current, remaining(deadline)));
            int status = response.statusCode();
            if (status >= 300 && status < 400) {
                String location = response.headers().firstValue("location").orElse("");
                closeQuietly(response);
                if (location.isBlank()) {
                    throw new IllegalStateException("重定向缺 Location 头: " + current);
                }
                // 在跟随处判上限：hops 是已跟随的跳数，允许恰好 maxRedirects 跳
                if (hops >= maxRedirects) {
                    throw new IllegalStateException("重定向超过 " + maxRedirects + " 跳: " + url);
                }
                current = validator.apply(current.resolve(location).toString());
                hops++;
                continue;
            }
            break;
        }
        try {
            if (response.statusCode() >= 400) {
                throw new IllegalStateException("下载失败: HTTP " + response.statusCode());
            }
            return readBody(response, url, deadline);
        } finally {
            closeQuietly(response);
        }
    }

    private HttpRequest request(URI uri, Duration timeout) {
        return HttpRequest.newBuilder().uri(uri).timeout(timeout).GET().build();
    }

    /** 剩余总预算耗尽即失败；单跳超时压到剩余预算内，保证总时长不超预算。 */
    private Duration remaining(long deadline) {
        long left = deadline - System.nanoTime();
        if (left <= 0) {
            throw new IllegalStateException("下载超时: 总预算耗尽");
        }
        Duration remaining = Duration.ofNanos(left);
        return remaining.compareTo(MAX_REQUEST_TIMEOUT) > 0 ? MAX_REQUEST_TIMEOUT : remaining;
    }

    private HttpResponse<InputStream> send(HttpRequest request) {
        try {
            return transport.send(request);
        } catch (IOException e) {
            throw new IllegalStateException("下载失败: " + e.getMessage(), e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("下载被中断", e);
        }
    }

    /**
     * Content-Length 超限先拒绝；流式读取中再兜底大小与总预算。
     *
     * <p>{@code HttpRequest.timeout} 只约束到响应头到达（用 ofInputStream 交付时），
     * 响应体不受它保护。没有逐块 deadline 检查的话，恶意站点回完 200 头再慢慢吐字节
     * 就能长期占住请求线程。</p>
     */
    private byte[] readBody(HttpResponse<InputStream> response, String url, long deadline) {
        long contentLength = response.headers().firstValueAsLong("content-length").orElse(-1);
        if (contentLength > maxBytes) {
            throw new IllegalArgumentException("响应超过大小上限 " + maxBytes + " 字节: " + url);
        }
        try (InputStream in = response.body()) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buffer = new byte[8192];
            long total = 0;
            int n;
            while ((n = in.read(buffer)) != -1) {
                if (System.nanoTime() - deadline > 0) {
                    throw new IllegalStateException("下载超时: 总预算耗尽");
                }
                total += n;
                if (total > maxBytes) {
                    throw new IllegalArgumentException("响应超过大小上限 " + maxBytes + " 字节: " + url);
                }
                out.write(buffer, 0, n);
            }
            return out.toByteArray();
        } catch (IOException e) {
            throw new IllegalStateException("读取响应失败: " + e.getMessage(), e);
        }
    }

    private static void closeQuietly(HttpResponse<InputStream> response) {
        if (response != null && response.body() != null) {
            try {
                response.body().close();
            } catch (IOException ignored) {
                // 关闭失败不影响结果：连接最终由 HttpClient 回收
            }
        }
    }

    private static HttpTransport defaultTransport() {
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        return request -> client.send(request, HttpResponse.BodyHandlers.ofInputStream());
    }
}
