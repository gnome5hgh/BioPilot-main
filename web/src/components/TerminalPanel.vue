<template>
  <div v-show="store.open" class="terminal-panel" :style="{ height: panelHeight + 'px' }">
    <div class="resize-handle" @mousedown.prevent="startResize"></div>
    <div class="panel-head">
      <div class="tab-row">
        <span class="tab active" title="终端运行在服务器上，拥有服务账号权限">终端 {{ store.shell }}</span>
        <span class="keep-hint">关闭面板不会结束会话</span>
      </div>
      <div class="panel-actions">
        <button class="icon" title="重新启动终端（会结束当前会话）" @click="restart">＋</button>
        <button class="icon" title="关闭面板（保留会话）" @click="store.hide()">×</button>
      </div>
    </div>
    <div v-if="!store.enabled" class="disabled">
      当前部署未启用宿主终端。<br />
      管理员可在 config.yaml 的 <code>runtime.allow_host_shell</code> 开启。
    </div>
    <div v-else ref="termBox" class="term-box"></div>
    <div v-if="disconnected && store.enabled" class="disconnect-bar">
      连接已断开
      <button class="btn btn-sm" @click="reconnect">重连</button>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import http from '../api/auth'
import { useTerminalStore } from '../stores/terminal'
import { confirmDialog } from '../utils/confirm'
import { errText } from '../utils/errors'
import { toast } from '../utils/toast'

const store = useTerminalStore()
const termBox = ref(null)
const panelHeight = ref(340)
const disconnected = ref(false)

let term = null
let fit = null
let ws = null
let inputDisposable = null
let resizeObserver = null
let initialized = false
let intentionalClose = false
let resizing = false

onMounted(async () => {
  await loadConfig()
  window.addEventListener('mousemove', onResizeMove)
  window.addEventListener('mouseup', stopResize)
  if (store.open) {
    await nextTick()
    initTerminal()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onResizeMove)
  window.removeEventListener('mouseup', stopResize)
  inputDisposable?.dispose()
  resizeObserver?.disconnect()
  intentionalClose = true
  closeSocket()
  term?.dispose()
})

watch(() => store.open, async (open) => {
  if (!open) return
  if (!initialized) {
    await nextTick()
    initTerminal()
  } else {
    await nextTick()
    fitTerm()
    term?.focus()
  }
})

watch(() => store.enabled, async (enabled) => {
  if (!enabled) {
    closeSocket()
    term?.dispose()
    term = null
    initialized = false
    return
  }
  if (store.open && !initialized) {
    await nextTick()
    initTerminal()
  }
})

async function loadConfig() {
  try {
    const { data } = await http.get('/terminal/config')
    store.setConfig(data)
  } catch {
    // 配置读不到时仍允许尝试连接；WS 会给出最终裁决
  }
}

function initTerminal() {
  if (initialized || !store.enabled || !termBox.value) return
  initialized = true
  term = new Terminal({
    fontSize: 13,
    cursorBlink: true,
    scrollback: 5000,
    theme: { background: '#1e1f24' },
  })
  fit = new FitAddon()
  term.loadAddon(fit)
  term.open(termBox.value)
  fitTerm()
  inputDisposable = term.onData((data) => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'input', data }))
    }
  })
  resizeObserver = new ResizeObserver(() => fitTerm())
  resizeObserver.observe(termBox.value)
  connect()
  term.focus()
}

function connect() {
  if (!term) return
  closeSocket()
  disconnected.value = false
  intentionalClose = false
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/api/ws/terminal`)
  ws.onopen = () => {
    disconnected.value = false
    sendResize()
    term.focus()
  }
  ws.onmessage = (event) => term.write(event.data)
  ws.onclose = (event) => {
    if (intentionalClose) return
    disconnected.value = true
    if (event.reason) {
      term.write(`\r\n\x1b[33m[${event.reason}]\x1b[0m\r\n`)
    }
  }
  ws.onerror = () => {
    disconnected.value = true
  }
}

function closeSocket() {
  if (!ws) return
  intentionalClose = true
  ws.onclose = null
  ws.onerror = null
  ws.close()
  ws = null
}

function reconnect() {
  // 重新附着会回放整个缓冲；先清屏，避免在已有内容上再叠一份
  term?.reset()
  connect()
  toast('正在重新连接终端', 'info', 1600)
}

function sendResize() {
  if (ws?.readyState !== WebSocket.OPEN || !term) return
  ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
}

function fitTerm() {
  if (!fit) return
  try {
    fit.fit()
  } catch {
    return
  }
  sendResize()
}

async function restart() {
  const ok = await confirmDialog({
    title: '重新启动终端',
    message: '当前终端里的进程会被结束，重新打开一个干净的 shell。',
    detail: '历史输出会清空；正在运行的任务会中断。',
    confirmText: '重新启动',
    danger: true,
  })
  if (!ok) return
  try {
    await http.post('/terminal/restart')
    closeSocket()
    term?.reset()
    disconnected.value = false
    connect()
    toast('终端已重启', 'success')
  } catch (error) {
    toast(errText(error, '终端重启失败'), 'error')
  }
}

function startResize(event) {
  resizing = true
  event.preventDefault()
}

function onResizeMove(event) {
  if (!resizing) return
  const next = window.innerHeight - event.clientY
  panelHeight.value = Math.min(Math.max(next, 160), Math.round(window.innerHeight * 0.72))
  nextTick(fitTerm)
}

function stopResize() {
  resizing = false
}
</script>

<style scoped>
.terminal-panel {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 70;
  background: #1e1f24;
  color: #d6d8de;
  border-top: 1px solid #34363d;
  display: flex;
  flex-direction: column;
  box-shadow: 0 -12px 32px rgba(20, 24, 34, 0.24);
}

.resize-handle {
  height: 6px;
  cursor: ns-resize;
  background: linear-gradient(#3a3c44, #26272d);
}
.resize-handle:hover { background: #2ec5b1; opacity: 0.6; }

.panel-head {
  flex: none;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  background: #26272d;
  border-bottom: 1px solid #34363d;
}
.tab-row { display: flex; align-items: center; gap: 10px; min-width: 0; }
.tab {
  font-size: 12px;
  color: #d6d8de;
  background: #1e1f24;
  border-radius: 6px;
  padding: 4px 10px;
  white-space: nowrap;
}
.tab.active { color: #fff; }
.keep-hint { font-size: 11px; color: #7a7f8c; }
.panel-actions { display: flex; align-items: center; gap: 2px; }
.icon {
  border: none;
  background: transparent;
  color: #b7bdc9;
  font-size: 16px;
  cursor: pointer;
  width: 28px;
  height: 26px;
  border-radius: 6px;
}
.icon:hover { background: #34363d; color: #fff; }

.term-box { flex: 1; min-height: 0; padding: 6px 8px; }
.disabled {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #9aa0ad;
  font-size: 13px;
  line-height: 1.9;
}
.disabled code { color: #2ec5b1; }
.disconnect-bar {
  position: absolute;
  right: 16px;
  bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: #3a2a2a;
  color: #fca5a5;
  border: 1px solid #7f1d1d;
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 12px;
}
.disconnect-bar .btn { background: #fff; color: #2f3033; border: none; }
</style>
