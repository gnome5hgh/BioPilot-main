package com.biopilot.common.net;

import org.junit.jupiter.api.Test;

import java.net.URI;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/** UrlGuard：外部 URL 只放行公网 http(s)。IP 字面量用例不依赖 DNS。 */
class UrlGuardTest {

    @Test
    void rejectsLoopback() {
        assertThrows(IllegalArgumentException.class,
                () -> UrlGuard.validateExternal("http://127.0.0.1/x.pdf"));
    }

    @Test
    void rejectsPrivateRanges() {
        assertThrows(IllegalArgumentException.class, () -> UrlGuard.validateExternal("http://10.0.0.5/x"));
        assertThrows(IllegalArgumentException.class, () -> UrlGuard.validateExternal("http://192.168.1.1/x"));
        assertThrows(IllegalArgumentException.class, () -> UrlGuard.validateExternal("http://172.16.0.5/x"));
    }

    @Test
    void rejectsLinkLocalAndMetadata() {
        assertThrows(IllegalArgumentException.class,
                () -> UrlGuard.validateExternal("http://169.254.169.254/latest/meta-data"));
        assertThrows(IllegalArgumentException.class,
                () -> UrlGuard.validateExternal("http://metadata.google.internal/x"));
    }

    @Test
    void rejectsIpv6UniqueLocal() {
        // fc00::/7 是 isSiteLocalAddress（fec0::/10）覆盖不到的 ULA 段，必须单独拦
        assertThrows(IllegalArgumentException.class,
                () -> UrlGuard.validateExternal("http://[fc00::1]/x"));
        assertThrows(IllegalArgumentException.class,
                () -> UrlGuard.validateExternal("http://[fd12::1]/x"));
    }

    @Test
    void rejectsNonHttpSchemes() {
        assertThrows(IllegalArgumentException.class, () -> UrlGuard.validateExternal("file:///etc/passwd"));
        assertThrows(IllegalArgumentException.class, () -> UrlGuard.validateExternal("ftp://example.com/x"));
    }

    @Test
    void rejectsMissingHost() {
        assertThrows(IllegalArgumentException.class, () -> UrlGuard.validateExternal("http:///path/x"));
    }

    @Test
    void rejectsUnresolvableHost() {
        // .invalid 是 RFC 2606 保留 TLD，保证解析失败 → fail-closed
        assertThrows(IllegalArgumentException.class,
                () -> UrlGuard.validateExternal("http://nonexistent.invalid/x"));
    }

    @Test
    void allowsPublicIpLiteral() {
        URI uri = UrlGuard.validateExternal("http://8.8.8.8/paper.pdf");
        assertEquals("8.8.8.8", uri.getHost());
    }

    @Test
    void allowsPublicHostname() {
        URI uri = UrlGuard.validateExternal("https://example.com/paper.pdf");
        assertEquals("example.com", uri.getHost());
    }
}
