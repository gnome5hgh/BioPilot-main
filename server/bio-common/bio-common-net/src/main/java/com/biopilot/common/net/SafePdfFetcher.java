package com.biopilot.common.net;

import java.time.Duration;

/**
 * 带 SSRF 防护的 PDF 下载：只允许公网 http(s)，逐跳校验重定向，响应必须是 %PDF。
 *
 * <p>服务两处调用：平台文献导入（按 DOI/链接抓全文）与引擎内部端点
 * {@code /internal/literature/fetch-pdf}（agent 经平台下载）。总时间预算压在
 * 引擎侧 {@code platform.transfer_timeout}（120 秒）之内。</p>
 */
public final class SafePdfFetcher {

    private static final int MAX_REDIRECTS = 5;
    private static final long MAX_BYTES = 200L * 1024 * 1024;
    private static final Duration TOTAL_BUDGET = Duration.ofSeconds(110);

    private static final SafeHttpFetcher FETCHER = new SafeHttpFetcher(MAX_BYTES);

    private SafePdfFetcher() {
    }

    /** 下载 PDF 字节；任一跳指向私网/回环/元数据端点即拒绝，响应必须是 %PDF。 */
    public static byte[] fetch(String url) {
        return fetch(FETCHER, url);
    }

    /** 供测试注入假传输；生产路径一律走上面的静态入口。 */
    static byte[] fetch(SafeHttpFetcher fetcher, String url) {
        byte[] data = fetcher.fetch(url, UrlGuard::validateExternal, MAX_REDIRECTS, TOTAL_BUDGET);
        if (data.length < 4 || data[0] != '%' || data[1] != 'P' || data[2] != 'D' || data[3] != 'F') {
            throw new IllegalArgumentException("响应不是 PDF（缺 %PDF magic bytes）: " + url);
        }
        return data;
    }
}
