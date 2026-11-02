package com.biopilot.common.web.http;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/** SSE 逐块转发：上游读到多少就写多少并立即 flush。

    不能用 transferTo：它会攒满内部缓冲区才写出，短回答会变成「突然全部出现」。
    SSE 的可见节奏必须由上游每一帧决定，代理只做搬运。
*/
public final class SseRelay {

    private SseRelay() {
    }

    /**
     * 把上游 SSE 字节流逐块写到下游并 flush。
     *
     * @param upstream 上游响应体（由调用方负责关闭）
     * @param out      下游输出流
     * @throws IOException 读写失败（客户端断开等）
     */
    public static void pump(InputStream upstream, OutputStream out) throws IOException {
        byte[] buffer = new byte[1024];
        int read;
        while ((read = upstream.read(buffer)) != -1) {
            out.write(buffer, 0, read);
            out.flush();
        }
    }
}
