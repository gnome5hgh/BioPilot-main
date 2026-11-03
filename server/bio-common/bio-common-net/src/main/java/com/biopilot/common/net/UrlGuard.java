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
        if (address instanceof Inet6Address) {
            return isForbiddenIpv6(bytes);
        }
        return bytes.length == 4 && isForbiddenIpv4(bytes);
    }

    /**
     * IPv4 保留/非全局路由段。
     *
     * <p>JDK 的 {@code isSiteLocalAddress} 只覆盖 10/8、172.16/12、192.168/16，
     * 漏掉 CGNAT（100.64/10，云厂商元数据 100.100.100.200 就在里面）、基准测试
     * （198.18/15）、192.0.0/24、文档地址与 240/4 保留段。这些地址在云环境里
     * 往往指向宿主/元数据服务，必须按内网处理。</p>
     */
    private static boolean isForbiddenIpv4(byte[] b) {
        int b0 = b[0] & 0xff;
        int b1 = b[1] & 0xff;
        int b2 = b[2] & 0xff;
        int b3 = b[3] & 0xff;
        if (b0 == 0) {
            return true;                       // 0.0.0.0/8 "this network"
        }
        if (b0 == 10 || b0 == 127) {
            return true;                       // 10/8 私网、127/8 回环
        }
        if (b0 == 172 && (b1 & 0xf0) == 16) {
            return true;                       // 172.16.0.0/12 私网
        }
        if (b0 == 192 && b1 == 168) {
            return true;                       // 192.168.0.0/16 私网
        }
        if (b0 == 169 && b1 == 254) {
            return true;                       // 169.254.0.0/16 链路本地/云元数据
        }
        if (b0 >= 224 && b0 <= 239) {
            return true;                       // 224.0.0.0/4 组播
        }
        if (b0 == 100 && (b1 & 0xc0) == 64) {
            return true;                       // 100.64.0.0/10 CGNAT / 云元数据
        }
        if (b0 == 198 && (b1 & 0xfe) == 18) {
            return true;                       // 198.18.0.0/15 基准测试
        }
        if (b0 == 192 && b1 == 0 && b2 == 0) {
            return true;                       // 192.0.0.0/24 IETF 协议分配
        }
        if ((b0 == 192 && b1 == 0 && b2 == 2)
                || (b0 == 198 && b1 == 51 && b2 == 100)
                || (b0 == 203 && b1 == 0 && b2 == 113)) {
            return true;                       // TEST-NET-1/2/3
        }
        if ((b0 & 0xf0) == 240) {
            return true;                       // 240.0.0.0/4 保留（含广播）
        }
        return b0 == 255 && b1 == 255 && b2 == 255 && b3 == 255;
    }

    /** IPv6 保留段：IPv4 映射/兼容地址要拆出内嵌 IPv4 再判，隧道机制一律拒绝。 */
    private static boolean isForbiddenIpv6(byte[] b) {
        if ((b[0] & 0xfe) == 0xfc) {
            return true;                       // fc00::/7 ULA
        }
        // ::ffff:a.b.c.d（IPv4 映射）：JDK 的 isLoopback/isSiteLocal 对此不可靠
        boolean mapped = true;
        for (int i = 0; i < 10; i++) {
            if (b[i] != 0) {
                mapped = false;
                break;
            }
        }
        if (mapped && (b[10] & 0xff) == 0xff && (b[11] & 0xff) == 0xff) {
            return isForbiddenIpv4(new byte[] {b[12], b[13], b[14], b[15]});
        }
        // ::a.b.c.d（IPv4 兼容地址）：前 12 字节全 0，后 4 字节是内嵌 IPv4
        boolean compatible = true;
        for (int i = 0; i < 12; i++) {
            if (b[i] != 0) {
                compatible = false;
                break;
            }
        }
        if (compatible) {
            return isForbiddenIpv4(new byte[] {b[12], b[13], b[14], b[15]});
        }
        // 2002::/16（6to4）与 2001:0::/32（Teredo）内嵌 IPv4，同样可绕过点分检查
        if ((b[0] & 0xff) == 0x20 && (b[1] & 0xff) == 0x02) {
            return true;
        }
        return (b[0] & 0xff) == 0x20 && (b[1] & 0xff) == 0x01
                && (b[2] & 0xff) == 0x00 && (b[3] & 0xff) == 0x00;
    }
}
