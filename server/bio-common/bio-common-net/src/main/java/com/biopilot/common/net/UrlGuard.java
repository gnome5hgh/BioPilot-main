package com.biopilot.common.net;

import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.URI;
import java.util.Locale;

/**
 * 外部 URL 安全校验：只放行公网 http(s) 地址。
 *
 * <p>服务「外部内容带来的 URL」这一类目的地（搜索结果里的 PDF 链接、文献导入地址）：
 * 把主机名解析为全部 IP 后，拒绝回环、私网、链路本地、ULA（fc00::/7）、组播与
 * 任意地址，并硬拦云元数据端点；DNS 解析失败按拒绝处理（fail-closed）。</p>
 *
 * <p>只校验外部 URL。管理员配置的内部服务地址（MCP 检索源、引擎回调、推理端点等）
 * 必须能连内网，不属于本类职责——不要把这里套到配置化端点上。</p>
 */
public final class UrlGuard {

    private UrlGuard() {
    }

    /**
     * 校验 URL 并返回解析后的 {@link URI}。
     *
     * @param url 待校验的外部地址
     * @return 解析后的 URI
     * @throws IllegalArgumentException scheme 非 http/https、缺 host、命中云元数据、
     *         解析地址落在保留区间，或 DNS 解析失败
     */
    public static URI validateExternal(String url) {
        URI uri;
        try {
            uri = URI.create(url);
        } catch (Exception e) {
            throw new IllegalArgumentException("非法 URL: " + url);
        }
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        if (!scheme.equals("http") && !scheme.equals("https")) {
            throw new IllegalArgumentException("只允许 http/https 访问: " + url);
        }
        String host = uri.getHost();
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("URL 缺少 host: " + url);
        }
        String lower = host.toLowerCase(Locale.ROOT);
        if (lower.equals("metadata.google.internal") || lower.equals("169.254.169.254")) {
            throw new IllegalArgumentException("禁止访问云元数据端点: " + host);
        }
        InetAddress[] addresses;
        try {
            addresses = InetAddress.getAllByName(host);
        } catch (Exception e) {
            throw new IllegalArgumentException("无法解析地址: " + host, e);
        }
        for (InetAddress address : addresses) {
            if (isForbidden(address)) {
                throw new IllegalArgumentException("禁止访问内网/回环地址: " + host);
            }
        }
        return uri;
    }

    /** 任一解析地址落在保留区间即拒绝；IPv6 ULA（fc00::/7）是 isSiteLocalAddress 覆盖不到的一段。 */
    private static boolean isForbidden(InetAddress address) {
        if (address.isAnyLocalAddress() || address.isLoopbackAddress()
                || address.isLinkLocalAddress() || address.isSiteLocalAddress()
                || address.isMulticastAddress()) {
            return true;
        }
        byte[] bytes = address.getAddress();
        return address instanceof Inet6Address && bytes.length == 16 && (bytes[0] & 0xfe) == 0xfc;
    }
}
