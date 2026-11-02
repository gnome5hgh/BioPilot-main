package com.biopilot.common.web.http;

import java.net.InetAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Locale;

/** 带 SSRF 防护的 PDF 下载：只允许公网 http(s)，逐跳校验重定向，响应必须是 %PDF。 */
public final class SafePdfFetcher {

    private static final int MAX_REDIRECTS = 5;
    private static final long MAX_BYTES = 200L * 1024 * 1024;

    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    private SafePdfFetcher() {
    }

    /** 下载 PDF 字节；任一跳指向私网/回环/元数据端点即拒绝。 */
    public static byte[] fetch(String url) {
        validate(url);
        String current = url;
        HttpResponse<byte[]> response = null;
        for (int i = 0; i < MAX_REDIRECTS; i++) {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(current))
                    .timeout(Duration.ofSeconds(30))
                    .GET()
                    .build();
            try {
                response = CLIENT.send(request, HttpResponse.BodyHandlers.ofByteArray());
            } catch (Exception e) {
                throw new IllegalStateException("下载失败: " + e.getMessage(), e);
            }
            int status = response.statusCode();
            if (status >= 300 && status < 400) {
                String location = response.headers().firstValue("location").orElse("");
                if (location.isBlank()) {
                    throw new IllegalStateException("重定向缺 Location 头: " + current);
                }
                current = URI.create(current).resolve(location).toString();
                validate(current);
                continue;
            }
            break;
        }
        if (response == null) {
            throw new IllegalStateException("下载失败: 无响应");
        }
        if (response.statusCode() >= 400) {
            throw new IllegalStateException("下载失败: HTTP " + response.statusCode());
        }
        byte[] data = response.body();
        if (data == null || data.length < 4 || data[0] != '%' || data[1] != 'P'
                || data[2] != 'D' || data[3] != 'F') {
            throw new IllegalArgumentException("响应不是 PDF（缺 %PDF magic bytes）: " + url);
        }
        if (data.length > MAX_BYTES) {
            throw new IllegalArgumentException("PDF 超过大小上限");
        }
        return data;
    }

    private static void validate(String url) {
        URI uri;
        try {
            uri = URI.create(url);
        } catch (Exception e) {
            throw new IllegalArgumentException("非法 URL: " + url);
        }
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        if (!scheme.equals("http") && !scheme.equals("https")) {
            throw new IllegalArgumentException("只允许 http/https 下载");
        }
        String host = uri.getHost();
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("URL 缺少 host");
        }
        String lower = host.toLowerCase(Locale.ROOT);
        if (lower.equals("metadata.google.internal") || lower.equals("169.254.169.254")) {
            throw new IllegalArgumentException("禁止访问云元数据端点");
        }
        try {
            for (InetAddress address : InetAddress.getAllByName(host)) {
                if (address.isAnyLocalAddress() || address.isLoopbackAddress()
                        || address.isLinkLocalAddress() || address.isSiteLocalAddress()
                        || address.isMulticastAddress()) {
                    throw new IllegalArgumentException("禁止访问内网/回环地址: " + host);
                }
            }
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalArgumentException("无法解析下载地址: " + host, e);
        }
    }
}
