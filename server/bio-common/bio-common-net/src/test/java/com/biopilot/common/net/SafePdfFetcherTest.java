package com.biopilot.common.net;

import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpHeaders;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** SafeHttpFetcher / SafePdfFetcher：逐跳校验、%PDF 校验、大小上限、跳数上限（假传输）。 */
class SafePdfFetcherTest {

    /** 校验放行一切的假校验器：SafePdfFetcher 固定用 UrlGuard，fetcher 语义单测用宽松校验。 */
    private static final Function<String, URI> NO_OP = URI::create;

    /** 固定响应队列的假传输：记录收到的请求 URI，队列取空再请求即失败。 */
    private static SafeHttpFetcher.HttpTransport transportOf(Deque<String> seen,
                                                             FakeResponse... responses) {
        Deque<FakeResponse> queue = new ArrayDeque<>(List.of(responses));
        return request -> {
            seen.add(request.uri().toString());
            FakeResponse next = queue.poll();
            if (next == null) {
                throw new java.io.IOException("无更多假响应");
            }
            return next.asResponse();
        };
    }

    private static SafeHttpFetcher fetcher(long maxBytes, FakeResponse... responses) {
        return new SafeHttpFetcher(maxBytes, transportOf(new ArrayDeque<>(), responses));
    }

    private static byte[] fetchThroughGuard(SafeHttpFetcher.HttpTransport transport, String url) {
        return new SafeHttpFetcher(1_000_000, transport)
                .fetch(url, UrlGuard::validateExternal, 5, Duration.ofSeconds(110));
    }

    @Test
    void followsRedirectsAndValidatesEveryHop() {
        // 302 → 相对 Location → 200：真实 GET 链逐跳跟随，两跳都真实发出
        Deque<String> seen = new ArrayDeque<>();
        SafeHttpFetcher.HttpTransport transport = transportOf(seen,
                FakeResponse.redirect("http://8.8.8.8/a.pdf", "/real.pdf"),
                FakeResponse.ok("%PDF-1.4 fake".getBytes()));
        byte[] data = new SafeHttpFetcher(1_000_000, transport)
                .fetch("http://8.8.8.8/a.pdf", NO_OP, 5, Duration.ofSeconds(110));
        assertArrayEquals("%PDF-1.4 fake".getBytes(), data);
        assertTrue(seen.contains("http://8.8.8.8/real.pdf"), "重定向目标应被真实请求");
    }

    @Test
    void rejectsRedirectToPrivateAddress() {
        // 真实 UrlGuard：重定向跳进私网当场拒绝
        SafeHttpFetcher.HttpTransport transport = transportOf(new ArrayDeque<>(),
                FakeResponse.redirect("http://8.8.8.8/a.pdf", "http://10.0.0.1/x.pdf"));
        assertThrows(IllegalArgumentException.class,
                () -> fetchThroughGuard(transport, "http://8.8.8.8/a.pdf"));
    }

    @Test
    void rejectsTooManyRedirects() {
        SafeHttpFetcher.HttpTransport transport =
                request -> FakeResponse.redirect(request.uri().toString(), "/next.pdf").asResponse();
        SafeHttpFetcher fetcher = new SafeHttpFetcher(1_000_000, transport);
        IllegalStateException e = assertThrows(IllegalStateException.class,
                () -> fetcher.fetch("http://8.8.8.8/a.pdf", NO_OP, 1, Duration.ofSeconds(110)));
        assertTrue(e.getMessage().contains("重定向超过 1 跳"));
    }

    @Test
    void rejectsRedirectWithoutLocation() {
        SafeHttpFetcher fetcher = fetcher(1_000_000,
                FakeResponse.of(302, HttpHeaders.of(Map.of(), (k, v) -> true), new byte[0]));
        assertThrows(IllegalStateException.class,
                () -> fetcher.fetch("http://8.8.8.8/a.pdf", NO_OP, 5, Duration.ofSeconds(110)));
    }

    @Test
    void rejectsHttpErrorStatus() {
        SafeHttpFetcher fetcher = fetcher(1_000_000, FakeResponse.ok("not found".getBytes(), 404));
        assertThrows(IllegalStateException.class,
                () -> fetcher.fetch("http://8.8.8.8/a.pdf", NO_OP, 5, Duration.ofSeconds(110)));
    }

    @Test
    void rejectsBodyOverLimitWhileStreaming() {
        // 无 Content-Length，靠流式读取兜底拒绝
        SafeHttpFetcher fetcher = fetcher(10, FakeResponse.ok(new byte[32]));
        assertThrows(IllegalArgumentException.class,
                () -> fetcher.fetch("http://8.8.8.8/a.pdf", NO_OP, 5, Duration.ofSeconds(110)));
    }

    @Test
    void rejectsContentLengthOverLimitWithoutReading() {
        SafeHttpFetcher fetcher = fetcher(10,
                FakeResponse.of(200, HttpHeaders.of(Map.of("content-length", List.of("1000000")),
                        (k, v) -> true), new byte[0]));
        assertThrows(IllegalArgumentException.class,
                () -> fetcher.fetch("http://8.8.8.8/a.pdf", NO_OP, 5, Duration.ofSeconds(110)));
    }

    @Test
    void safePdfFetcherRejectsNonPdfBody() {
        SafeHttpFetcher fake = fetcher(1_000_000, FakeResponse.ok("<html>login wall</html>".getBytes()));
        assertThrows(IllegalArgumentException.class,
                () -> SafePdfFetcher.fetch(fake, "http://8.8.8.8/a.pdf"));
    }

    @Test
    void safePdfFetcherAcceptsPdfBytes() {
        SafeHttpFetcher fake = fetcher(1_000_000, FakeResponse.ok("%PDF-1.4 real".getBytes()));
        byte[] data = SafePdfFetcher.fetch(fake, "http://8.8.8.8/a.pdf");
        assertArrayEquals("%PDF-1.4 real".getBytes(), data);
    }

    /** JDK HttpResponse 的最小假实现；头用 HttpHeaders.of 构造，避免 mock。 */
    private record FakeResponse(int status, HttpHeaders headers, byte[] body) {

        static FakeResponse ok(byte[] body) {
            return ok(body, 200);
        }

        static FakeResponse ok(byte[] body, int status) {
            return of(status, HttpHeaders.of(Map.of(), (k, v) -> true), body);
        }

        static FakeResponse redirect(String current, String location) {
            return of(302, HttpHeaders.of(Map.of("location", List.of(location)), (k, v) -> true),
                    new byte[0]);
        }

        static FakeResponse of(int status, HttpHeaders headers, byte[] body) {
            return new FakeResponse(status, headers, body);
        }

        HttpResponse<InputStream> asResponse() {
            return new HttpResponse<>() {
                @Override
                public int statusCode() {
                    return status;
                }

                @Override
                public HttpRequest request() {
                    return null;
                }

                @Override
                public java.util.Optional<HttpResponse<InputStream>> previousResponse() {
                    return java.util.Optional.empty();
                }

                @Override
                public HttpHeaders headers() {
                    return headers;
                }

                @Override
                public InputStream body() {
                    return new ByteArrayInputStream(body);
                }

                @Override
                public java.util.Optional<javax.net.ssl.SSLSession> sslSession() {
                    return java.util.Optional.empty();
                }

                @Override
                public URI uri() {
                    return null;
                }

                @Override
                public java.net.http.HttpClient.Version version() {
                    return java.net.http.HttpClient.Version.HTTP_1_1;
                }
            };
        }
    }
}
