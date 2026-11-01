<template>
  <div class="term">
    <div class="note">你的终端：跑的是你自己的 biopilot REPL（会话与本账号网页互通）。关闭页面即退出。</div>
    <div class="term-body" ref="termBox"></div>
  </div>
</template>

<script setup>
// 终端视图：xterm.js ↔ WebSocket（vite/同源代理到 SpringBoot /ws/terminal，
// Java 中继注入 X-User-Id 转发到适配层 PTY 里的 biopilot REPL）。
// 登录态经 satoken cookie 自动携带；连接由服务端在退出/断开时收敛。
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'

const termBox = ref(null)
let term = null
let ws = null
let fit = null

onMounted(() => {
  term = new Terminal({
    fontSize: 13,
    cursorBlink: true,
    theme: { background: '#1e1f24' },
  })
  fit = new FitAddon()
  term.loadAddon(fit)
  term.open(termBox.value)
  fit.fit()

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/api/ws/terminal`)
  ws.onmessage = (e) => term.write(e.data)
  ws.onclose = () => term.write('\r\n\x1b[33m[连接已断开，刷新页面重连]\x1b[0m\r\n')
  ws.onerror = () => term.write('\r\n\x1b[31m[连接失败：请确认服务已启动]\x1b[0m\r\n')
  term.onData((d) => { if (ws.readyState === WebSocket.OPEN) ws.send(d) })

  window.addEventListener('resize', onResize)
})

function onResize() {
  if (fit) fit.fit()
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (ws) ws.close()
  if (term) term.dispose()
})
</script>

<style scoped>
.term { padding: 12px; height: 100%; display: flex; flex-direction: column; }
.term-body { background: #1e1f24; border-radius: 10px; padding: 10px; flex: 1; min-height: 0; }
.note { font-size: 12px; color: #818999; margin-bottom: 8px; }
</style>
