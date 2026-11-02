<template>
  <div class="chat-page">
    <header class="chat-head">
      <div class="title-wrap">
        <h1 class="chat-title">{{ store.currentTitle }}</h1>
        <span v-if="store.currentProject" class="project-chip">📁 {{ store.currentProject.name }}</span>
        <span v-else-if="!store.isDraft" class="project-chip muted">未归属项目</span>
      </div>
      <div class="head-right">
        <button class="terminal-btn" title="打开终端（会话会保留）" aria-label="打开终端"
                @click="terminalStore.toggle()">&gt;_</button>
        <select v-if="store.models.length > 1" class="select model-select"
                :value="store.selectedModel" @change="changeModel">
          <option v-for="model in store.models" :key="model.name" :value="model.name">
            {{ model.name }}
          </option>
        </select>
      </div>
    </header>

    <div ref="msgBox" class="messages" @scroll="onScroll">
      <div v-if="store.loadingHistory" class="empty">正在读取会话…</div>

      <template v-else-if="store.messages.length === 0">
        <div class="hero">
          <div class="hero-title">今天想让 BioPilot 做什么？</div>
          <div class="hero-sub">找论文、读论文、分析数据、写笔记、管引用。直接开始，不必先建项目。</div>
          <div class="cap-bar">
            <button v-for="cap in caps" :key="cap.name" class="cap"
                    :class="{ active: cap === currentCap }" @click="fillExample(cap)">
              {{ cap.name }}
            </button>
          </div>
          <button class="example" @click="fillExample(currentCap)">
            {{ currentCap.example }}
          </button>
        </div>
      </template>

      <div v-for="(message, index) in store.messages" :key="index"
           class="row" :class="message.role">
        <template v-if="message.role === 'user'">
          <div class="user-stack">
            <div v-if="message.attachments?.length" class="msg-files">
              <button v-for="(item, i) in message.attachments" :key="`${attachmentKey(item)}-${i}`"
                      class="file-card" :title="`预览 ${item.name}`" @click="openAttachment(item)">
                <span class="file-card-icon">{{ fileIcon(item) }}</span>
                <span class="file-card-body">
                  <span class="file-card-name">{{ item.name }}</span>
                  <span class="file-card-meta">{{ chipMeta(item) }}</span>
                </span>
              </button>
            </div>
            <div class="bubble user-bubble">{{ message.text }}</div>
          </div>
        </template>
        <template v-else>
          <div class="assistant-block">
            <div v-if="hasProcess(message)" class="thinking">
              <button class="thinking-head" @click="toggleThinking(message)">
                <span class="thinking-icon">{{ message.streaming && !message.text ? '◌' : '✓' }}</span>
                <span>{{ thinkingLabel(message) }}</span>
                <span class="thinking-chev">{{ message.thinkingOpen ? '▾' : '▸' }}</span>
              </button>
              <div v-if="message.thinkingOpen" class="thinking-body">
                <pre v-if="message.reasoning" class="reasoning">{{ message.reasoning }}</pre>
                <div v-if="message.activity.length" class="activity">
                  <div v-for="(item, i) in message.activity" :key="i" class="activity-line">
                    <span class="activity-state" :class="item.state">
                      {{ item.state === 'running' ? '◌' : item.state === 'error' ? '✕' : '✓' }}
                    </span>
                    <span class="activity-name">{{ prettyTool(item.name) }}</span>
                    <span v-if="item.duration" class="activity-time">{{ item.duration }}s</span>
                  </div>
                </div>
                <div v-if="!message.reasoning && !message.activity.length" class="reasoning muted">
                  正在思考…
                </div>
              </div>
            </div>

            <div v-if="message.error" class="error-banner">{{ message.error }}</div>

            <div v-if="message.text" class="bubble assistant-bubble">
              <MarkdownView :content="message.text" />
              <span v-if="message.streaming" class="cursor" aria-hidden="true">▌</span>
            </div>
            <div v-else-if="message.streaming && !hasProcess(message)" class="waiting">
              <span class="waiting-dot"></span>
              正在思考… {{ message.elapsed ? `(${message.elapsed}s)` : '' }}
            </div>

            <div v-if="message.text && !message.streaming" class="msg-actions">
              <button class="btn-link" @click="copyMessage(message)">复制</button>
              <span class="msg-time">{{ message.elapsed ? `用时 ${message.elapsed}s` : '' }}</span>
            </div>
          </div>
        </template>
      </div>
      <div v-if="!shouldStick && busy" class="stick-btn" @click="forceScroll">
        回到最新 ↓
      </div>
    </div>

    <footer class="composer">
      <div v-if="store.isDraft" class="composer-hint">
        <span v-if="store.currentProject">📁 将归入「{{ store.currentProject.name }}」</span>
        <span v-else>未选择项目，发送后进入任务列表</span>
      </div>
      <div v-else-if="store.currentProject" class="composer-hint">
        📁 {{ store.currentProject.name }}
      </div>

      <div v-if="attachments.length" class="attach-chips">
        <span v-for="item in attachments" :key="attachmentKey(item)" class="chip">
          <span class="chip-icon">{{ fileIcon(item) }}</span>
          <span class="chip-body">
            <span class="chip-name">{{ item.name }}</span>
            <span class="chip-meta">
              {{ chipMeta(item) }}
              <span v-if="item.notIndexed" class="chip-warn">未加入知识库</span>
            </span>
          </span>
          <button class="chip-x" title="移除附件" @click="removeAttachment(item)">×</button>
        </span>
      </div>

      <div class="input-box">
        <textarea v-model="input" :placeholder="placeholder" :disabled="busy"
                  @keydown.enter.exact.prevent="send"></textarea>
        <div class="input-controls">
          <div class="controls-left">
            <input ref="fileInput" type="file" class="file-hidden" multiple
                   accept=".csv,.tsv,.xlsx,.xls,.h5ad,.json,.txt,.md,.fasta,.fastq,.pdf"
                   @change="uploadFiles" />
            <button class="icon-btn" title="上传数据文件" :disabled="uploading"
                    @click="fileInput?.click()">{{ uploading ? '…' : '＋' }}</button>
            <button class="icon-btn" title="引用已上传的文件" @click="togglePicker">📎</button>
            <select v-if="store.isDraft" class="select project-select"
                    :value="store.currentProjectId" @change="changeProject">
              <option value="">不归属项目</option>
              <option v-for="project in store.projects" :key="project.projectId"
                      :value="project.projectId">{{ project.name }}</option>
            </select>

            <div class="ctx-wrap" @mouseenter="usageHover = true" @mouseleave="usageHover = false">
              <span class="ctx-pill" :class="usageLevel">
                上下文 {{ store.usage ? usagePercent + '%' : '—' }}
              </span>
              <div v-if="store.usage && usageHover" class="ctx-panel">
                <div class="ctx-head">上下文容量 {{ store.usage.total }}/{{ store.usage.limit }}</div>
                <div class="ctx-bar"><div class="ctx-fill" :style="{ width: usagePercent + '%' }"></div></div>
                <div v-for="(value, key) in store.usage.parts" :key="key" class="ctx-row">
                  <span>{{ ctxLabel(key) }}</span><span>{{ value }}</span>
                </div>
              </div>
            </div>
          </div>
          <button class="send" :class="{ stop: busy }" :title="busy ? '中断回答' : '发送'"
                  @click="busy ? stopStreaming() : send()">{{ busy ? '■' : '↑' }}</button>
        </div>
      </div>

      <template v-if="pickerOpen">
        <div class="picker-mask" @click="pickerOpen = false"></div>
        <div class="picker">
          <div class="picker-head">
            <input v-model="pickerQuery" class="input picker-search" placeholder="搜索论文或数据文件…" />
            <button class="btn btn-sm" @click="pickerOpen = false">完成</button>
          </div>
          <div class="picker-body">
            <div class="picker-group" v-if="visiblePapers.length">
              <div class="picker-label">论文</div>
              <button v-for="paper in visiblePapers" :key="paper.id" class="picker-item"
                      :class="{ picked: isPickedPaper(paper) }" @click="togglePaper(paper)">
                <span class="picker-check">{{ isPickedPaper(paper) ? '✓' : '' }}</span>
                <span class="picker-main">
                  <span class="picker-name">{{ paper.file_name || paper.title || '未命名论文' }}</span>
                  <span class="picker-meta">{{ paperMeta(paper) }}</span>
                </span>
              </button>
            </div>
            <div class="picker-group" v-if="visibleFiles.length">
              <div class="picker-label">数据文件</div>
              <button v-for="file in visibleFiles" :key="file.id" class="picker-item"
                      :class="{ picked: isPickedFile(file) }" @click="toggleFile(file)">
                <span class="picker-check">{{ isPickedFile(file) ? '✓' : '' }}</span>
                <span class="picker-main">
                  <span class="picker-name">{{ file.name }}</span>
                  <span class="picker-meta">{{ fileMeta(file) }}</span>
                </span>
              </button>
            </div>
            <div v-if="!visiblePapers.length && !visibleFiles.length" class="empty picker-empty">
              <div>{{ pickerQuery ? '没有匹配的文件' : '还没有可引用的论文或数据文件' }}</div>
              <router-link to="/papers">去文件管理上传 →</router-link>
            </div>
          </div>
        </div>
      </template>
    </footer>

    <div v-if="pendingConfirm" class="confirm-mask">
      <div class="confirm-card" role="alertdialog" aria-modal="true">
        <div class="confirm-title">需要你确认</div>
        <div class="confirm-summary">
          {{ pendingConfirm.tool_name || '工具调用' }}
          <span v-if="pendingConfirm.risk_level" class="badge badge-danger">{{ riskLabel(pendingConfirm.risk_level) }}</span>
        </div>
        <div v-if="pendingConfirm.cause" class="confirm-cause">{{ causeLabel(pendingConfirm.cause) }}</div>
        <div v-if="pendingConfirm.side_effects?.length" class="confirm-effects">
          副作用：{{ pendingConfirm.side_effects.join('、') }}
        </div>
        <div v-if="paramRows.length" class="confirm-params">
          <div v-for="row in paramRows" :key="row.key" class="param-row">
            <span class="param-key">{{ row.key }}</span>
            <pre class="param-value">{{ row.value }}</pre>
          </div>
        </div>
        <div class="confirm-timer">自动拒绝倒计时 {{ confirmRemaining }}s</div>
        <div class="confirm-actions">
          <button class="btn" @click="answerConfirm(false)">拒绝</button>
          <button class="btn btn-primary" @click="answerConfirm(true)">批准</button>
        </div>
      </div>
    </div>

    <FilePreviewModal :target="previewTarget" @close="previewTarget = null" />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import FilePreviewModal from '../components/FilePreviewModal.vue'
import MarkdownView from '../components/MarkdownView.vue'
import http from '../api/auth'
import { useChatStore } from '../stores/chat'
import { useTerminalStore } from '../stores/terminal'
import { toast } from '../utils/toast'
import { errText } from '../utils/errors'
import { fmtBytes } from '../utils/time'

const store = useChatStore()
const terminalStore = useTerminalStore()

const caps = [
  { name: '生信分析', example: '示例：帮我整理单细胞 QC 的标准流程要点' },
  { name: '文献解析', example: '示例：帮我总结一篇论文的核心观点与图表结论' },
  { name: '知识解读', example: '示例：什么是单细胞测序技术？' },
  { name: '文档写作', example: '示例：帮我写一份空间组学的综述大纲' },
]

const input = ref('')
const busy = ref(false)
const currentCap = ref(caps[0])
const attachments = ref([])
const papers = ref([])
const dataFiles = ref([])
const pickerOpen = ref(false)
const pickerQuery = ref('')
const usageHover = ref(false)
const pendingConfirm = ref(null)
const previewTarget = ref(null)
const confirmRemaining = ref(0)
const shouldStick = ref(true)
const uploading = ref(false)
const msgBox = ref(null)
const fileInput = ref(null)

let abortController = null
let tickTimer = null
let confirmTimer = null

const placeholder = '给 BioPilot 发送消息…（Enter 发送，Shift+Enter 换行）'

const usagePercent = computed(() => {
  const usage = store.usage
  if (!usage || !usage.limit) return 0
  return Math.min(100, Math.round((usage.total / usage.limit) * 1000) / 10)
})

const usageLevel = computed(() => {
  const percent = usagePercent.value
  return percent > 80 ? 'danger' : percent > 50 ? 'warn' : 'ok'
})

const paramRows = computed(() => {
  const params = pendingConfirm.value?.params || {}
  return Object.entries(params).map(([key, value]) => ({ key, value: String(value) }))
})

const visiblePapers = computed(() => {
  const text = pickerQuery.value.trim().toLowerCase()
  if (!text) return papers.value
  return papers.value.filter((paper) =>
    (paper.file_name || paper.title || '').toLowerCase().includes(text))
})

const visibleFiles = computed(() => {
  const text = pickerQuery.value.trim().toLowerCase()
  if (!text) return dataFiles.value
  return dataFiles.value.filter((file) => file.name.toLowerCase().includes(text))
})

onMounted(async () => {
  if (!store.initialized) await store.init()
  else if (!store.currentId) store.newDraft()
  applyPendingPrompt()
})

watch(() => store.pendingPrompt, applyPendingPrompt)

function applyPendingPrompt() {
  if (!store.pendingPrompt) return
  input.value = store.pendingPrompt
  store.pendingPrompt = ''
  nextTick(() => {
    scrollBottom()
  })
}

onBeforeUnmount(() => {
  stopTicker()
  stopConfirmTimer()
})

watch(() => store.currentId, () => {
  pendingConfirm.value = null
  previewTarget.value = null
  pickerOpen.value = false
  attachments.value = []
  stopConfirmTimer()
  nextTick(scrollBottom)
})

function fillExample(cap) {
  currentCap.value = cap
  input.value = cap.example.replace(/^示例：/, '')
}

function ctxLabel(key) {
  return {
    system_prompt: '系统提示词',
    skills: '技能',
    agents_list: '可派发清单',
    memory: '记忆块',
    intent: '意图规则',
    tools_schema: '工具定义',
    messages: '消息',
  }[key] || key
}

function scrollBottom() {
  if (!msgBox.value) return
  msgBox.value.scrollTop = msgBox.value.scrollHeight
}

function forceScroll() {
  shouldStick.value = true
  scrollBottom()
}

function onScroll() {
  const box = msgBox.value
  if (!box) return
  shouldStick.value = box.scrollHeight - box.scrollTop - box.clientHeight < 80
}

function maybeScroll() {
  if (!shouldStick.value) return
  // 数据刚改完时 DOM 还没长高，直接量 scrollHeight 会永远差一截；
  // 等一帧让浏览器完成布局再贴底。
  window.requestAnimationFrame(() => {
    if (shouldStick.value) scrollBottom()
  })
}

function startTicker(message) {
  stopTicker()
  tickTimer = window.setInterval(() => {
    if (message?.streaming) {
      message.elapsed = Math.floor((Date.now() - message.startedAt) / 1000)
    }
  }, 1000)
}

function stopTicker() {
  if (tickTimer) window.clearInterval(tickTimer)
  tickTimer = null
}

function hasProcess(message) {
  return Boolean(message.reasoning) || Boolean(message.activity?.length)
}

function thinkingLabel(message) {
  if (message.streaming && !message.text) {
    return `正在思考… ${message.elapsed ? `${message.elapsed}s` : ''}`
  }
  return message.reasoning
    ? `已思考（用时 ${message.elapsed || 0} 秒）`
    : `执行过程（用时 ${message.elapsed || 0} 秒）`
}

function toggleThinking(message) {
  message.thinkingOpen = !message.thinkingOpen
  message.thinkingTouched = true
}

function prettyTool(name) {
  const map = {
    rag_retrieve: '检索知识库',
    read_pdf: '读取论文',
    view_image: '查看图表',
    save_document: '保存文档',
    run_python: '执行分析代码',
    fetch_pdf: '下载论文',
    add_citation: '登记引用',
    glob: '查找文件',
    grep: '搜索文件内容',
    spawn_sub_agent: '派发子任务',
  }
  return map[name] || name || '工具调用'
}

function riskLabel(level) {
  return { low: '低风险', medium: '中风险', high: '高风险', critical: '严重' }[level] || level
}

function causeLabel(cause) {
  return {
    risk_threshold: '风险档位超过免问上限',
    path_fence: '写入位置超出允许范围',
    command: '命令需要人工判断',
  }[cause] || ''
}

function fileIcon(item) {
  const name = (item.name || '').toLowerCase()
  if (name.endsWith('.pdf')) return '📕'
  if (/\.(csv|tsv|xlsx|xls)$/.test(name)) return '📊'
  if (name.endsWith('.h5ad')) return '🧬'
  if (name.endsWith('.md') || name.endsWith('.txt')) return '📝'
  if (/\.(py|r)$/.test(name)) return '🐍'
  return '📎'
}

function chipMeta(item) {
  const name = (item.name || '').toLowerCase()
  const ext = name.includes('.') ? name.split('.').pop().toUpperCase() : ''
  const parts = []
  if (ext) parts.push(ext)
  if (item.size) parts.push(fmtBytes(item.size))
  return parts.join(' · ')
}

function attachmentKey(item) {
  return item.paper_id || item.file_id || item.name
}

function openAttachment(item) {
  if (item.paper_id) {
    previewTarget.value = { kind: 'paper', id: item.paper_id, name: item.name }
  } else if (item.file_id) {
    previewTarget.value = { kind: 'file', id: item.file_id, name: item.name }
  }
}

function isPickedPaper(paper) {
  return attachments.value.some((item) => item.paper_id === paper.id)
}

function isPickedFile(file) {
  return attachments.value.some((item) => item.file_id === file.id)
}

function paperMeta(paper) {
  const parts = []
  if (paper.kb_enabled === 1 || paper.indexed === 1) parts.push('已加入知识库')
  else parts.push('未加入知识库')
  if (paper.title && paper.file_name && paper.title !== paper.file_name) parts.push(paper.title)
  return parts.join(' · ')
}

function fileMeta(file) {
  return [file.content_type, file.size_bytes ? fmtBytes(file.size_bytes) : ''].filter(Boolean).join(' · ')
}

function togglePaper(paper) {
  if (isPickedPaper(paper)) {
    attachments.value = attachments.value.filter((item) => item.paper_id !== paper.id)
    return
  }
  attachments.value.push({
    paper_id: paper.id,
    oss_key: paper.oss_key,
    name: paper.file_name || paper.title || '未命名论文',
    size: paper.size_bytes,
    notIndexed: !(paper.kb_enabled === 1 || paper.indexed === 1),
  })
}

function toggleFile(file) {
  if (isPickedFile(file)) {
    attachments.value = attachments.value.filter((item) => item.file_id !== file.id)
    return
  }
  attachments.value.push({
    file_id: file.id,
    oss_key: file.oss_key,
    name: file.name,
    size: file.size_bytes,
    notIndexed: false,
  })
}

function removeAttachment(item) {
  attachments.value = attachments.value.filter((entry) => entry !== item)
}

async function togglePicker() {
  pickerOpen.value = !pickerOpen.value
  if (!pickerOpen.value) return
  pickerQuery.value = ''
  try {
    const [paperResp, fileResp] = await Promise.all([
      http.get('/agent/papers'),
      http.get('/agent/files'),
    ])
    papers.value = paperResp.data.papers || []
    dataFiles.value = fileResp.data.files || []
  } catch (error) {
    toast(errText(error, '文件清单加载失败'), 'error')
  }
}

async function uploadFiles(event) {
  const files = Array.from(event.target.files || [])
  if (!files.length) return
  uploading.value = true
  try {
    for (const file of files) {
      if (file.size > 100 * 1024 * 1024) {
        toast(`「${file.name}」超过 100MB 上限，已跳过`, 'error')
        continue
      }
      const form = new FormData()
      form.append('file', file)
      try {
        const { data } = await http.post('/agent/files/upload', form)
        attachments.value.push({ ...data, name: data.name || file.name, size: data.size || file.size })
        toast(`「${file.name}」已上传`, 'success')
      } catch (error) {
        toast(errText(error, `「${file.name}」上传失败`), 'error')
      }
    }
  } finally {
    uploading.value = false
    event.target.value = ''
  }
}

function changeProject(event) {
  store.setDraftProject(event.target.value)
}

async function changeModel(event) {
  await store.selectModel(event.target.value)
}

async function copyMessage(message) {
  try {
    await navigator.clipboard.writeText(message.text || '')
    toast('回答已复制', 'success', 1600)
  } catch {
    toast('复制失败，请手动选择文本', 'error')
  }
}

async function send() {
  const task = input.value.trim()
  if (!task || busy.value) return
  if (!store.currentId) store.newDraft(store.currentProjectId)

  input.value = ''
  const startedAt = Date.now()
  // 附件快照：request 末尾会清空附件栏，消息里要留一份用于渲染文件卡片与历史回放定位
  const sentAttachments = attachments.value.map((item) => ({
    ...(item.paper_id ? { paper_id: item.paper_id } : { file_id: item.file_id }),
    ...(item.oss_key ? { oss_key: item.oss_key } : {}),
    name: item.name,
    size: item.size || item.size_bytes || 0,
  }))
  const userMessage = { role: 'user', text: task, attachments: sentAttachments }
  // 必须是 reactive 代理：push 进数组后再经原始对象改字段不会触发视图更新
  const assistant = reactive({
    role: 'assistant',
    text: '',
    reasoning: '',
    activity: [],
    thinkingOpen: true,
    thinkingTouched: false,
    streaming: true,
    startedAt,
    elapsed: 0,
    error: '',
  })
  // 先登记会话行：后端要等 run 启动才落库，侧栏又只在 run 结束重拉，
  // 不登记的话新会话在整段回答期间都不会出现在左栏（含它所属的项目）
  if (!store.currentSession) store.registerSession(task)
  store.messages.push(userMessage, assistant)
  busy.value = true
  store.running = true
  shouldStick.value = true
  await nextTick()
  scrollBottom()
  startTicker(assistant)

  abortController = new AbortController()
  try {
    const response = await fetch('/api/agent/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        satoken: localStorage.getItem('biopilot_token') || '',
        'X-Conversation-Id': store.currentId,
      },
      body: JSON.stringify({
        task,
        conversation_id: store.currentId,
        project_id: store.currentProjectId || null,
        attachments: attachments.value,
      }),
      signal: abortController.signal,
    })

    if (response.status === 401) {
      toast('登录已失效，正在跳转登录页', 'error')
      setTimeout(() => { window.location.href = '/login' }, 800)
      return
    }
    if (!response.ok || !response.body) {
      let detail = `HTTP ${response.status}`
      try {
        const data = await response.json()
        detail = data.msg || detail
      } catch { /* 非 JSON 错误体保留状态码 */ }
      assistant.error = `对话失败：${detail}`
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let index
      while ((index = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, index)
        buffer = buffer.slice(index + 2)
        for (const line of frame.split('\n')) {
          if (!line.startsWith('data: ')) continue
          let event
          try {
            event = JSON.parse(line.slice(6))
          } catch {
            continue
          }
          handleEvent(event, assistant)
        }
      }
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      assistant.text = assistant.text ? `${assistant.text}\n\n[已中断]` : '[已中断]'
    } else {
      assistant.error = assistant.text ? `连接中断：${error.message}` : `对话失败：${error.message}`
    }
  } finally {
    busy.value = false
    store.running = false
    assistant.streaming = false
    assistant.elapsed = Math.floor((Date.now() - assistant.startedAt) / 1000)
    stopTicker()
    attachments.value = []
    await store.loadSessions()
    store.refreshUsage()
    await nextTick()
    maybeScroll()
  }
}

function handleEvent(event, assistant) {
  switch (event.type) {
    case 'reasoning':
      assistant.reasoning += event.text || ''
      if (!assistant.thinkingTouched) assistant.thinkingOpen = true
      break
    case 'content':
      assistant.text += event.text || ''
      // 回答开始后自动收起思考块，用户手动展开过就不再抢
      if (assistant.reasoning && !assistant.thinkingTouched && assistant.thinkingOpen) {
        assistant.thinkingOpen = false
      }
      break
    case 'tool_start':
      assistant.activity.push({
        name: event.tool_name || '工具',
        state: 'running',
        startedAt: Date.now(),
      })
      if (!assistant.reasoning && !assistant.thinkingTouched) assistant.thinkingOpen = true
      break
    case 'tool_end': {
      const running = [...assistant.activity].reverse().find(
        (item) => item.state === 'running' && (!event.tool_name || item.name === event.tool_name))
      if (running) {
        running.state = event.error ? 'error' : 'done'
        running.duration = event.duration_ms ? Math.round(event.duration_ms / 100) / 10 : 0
      }
      break
    }
    case 'done':
      if (event.text) assistant.text = event.text
      assistant.streaming = false
      break
    case 'error':
      assistant.error = `出错：${event.text || '未知错误'}`
      break
    case 'confirm':
      openConfirm(event)
      break
    default:
      break
  }
  maybeScroll()
}

function openConfirm(event) {
  pendingConfirm.value = event
  confirmRemaining.value = 300
  stopConfirmTimer()
  confirmTimer = window.setInterval(() => {
    confirmRemaining.value -= 1
    if (confirmRemaining.value <= 0) {
      stopConfirmTimer()
      pendingConfirm.value = null
      toast('确认已超时，服务端已按拒绝处理', 'error')
    }
  }, 1000)
}

function stopConfirmTimer() {
  if (confirmTimer) window.clearInterval(confirmTimer)
  confirmTimer = null
}

async function answerConfirm(approved) {
  const event = pendingConfirm.value
  pendingConfirm.value = null
  stopConfirmTimer()
  if (!event) return
  try {
    await fetch('/api/agent/chat/confirm', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        satoken: localStorage.getItem('biopilot_token') || '',
      },
      body: JSON.stringify({
        req_id: event.req_id,
        conversation_id: store.currentId,
        approved,
      }),
    })
  } catch (error) {
    toast(errText(error, '确认回传失败'), 'error')
  }
}

function stopStreaming() {
  abortController?.abort()
}
</script>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  min-width: 0;
}

.chat-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 24px;
  border-bottom: 1px solid #eef0f4;
}

.title-wrap { display: flex; align-items: center; gap: 10px; min-width: 0; }
.chat-title {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.project-chip {
  flex: none;
  font-size: 11px;
  color: #1f9e8c;
  background: #e8f8f5;
  border-radius: 999px;
  padding: 2px 9px;
}
.project-chip.muted { color: #818999; background: #f1f3f7; }
.head-right { display: flex; align-items: center; gap: 8px; }
.terminal-btn {
  border: 1px solid #e6e9ed;
  background: #fff;
  border-radius: 8px;
  height: 30px;
  padding: 0 9px;
  color: #4a5160;
  cursor: pointer;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 12px;
}
.terminal-btn:hover { border-color: #2ec5b1; color: #1f9e8c; }
.model-select { height: 30px; font-size: 12px; }

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 28px 32px 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  position: relative;
}

.hero { margin-top: 8vh; text-align: center; }
.hero-title { font-size: 30px; font-weight: 750; letter-spacing: 0.2px; }
.hero-sub { margin-top: 10px; color: #818999; font-size: 13px; }
.cap-bar { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; margin: 26px 0 14px; }
.cap {
  border: none;
  border-radius: 999px;
  padding: 8px 14px;
  background: #f4f6f9;
  color: #4a5160;
  font-size: 13px;
  cursor: pointer;
}
.cap:hover { background: #e8f8f5; color: #1f9e8c; }
.cap.active { background: #2ec5b1; color: #fff; }
.example {
  border: 1px solid #e6e9ed;
  background: #fff;
  border-radius: 10px;
  padding: 10px 16px;
  color: #818999;
  font-size: 13px;
  cursor: pointer;
  max-width: 560px;
}

.row { display: flex; }
.row.user { justify-content: flex-end; }
.user-stack {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  max-width: 76%;
  min-width: 0;
}
.msg-files {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  max-width: 100%;
}
.file-card {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 180px;
  max-width: 320px;
  padding: 9px 12px;
  background: #fff;
  border: 1px solid #e6e9ed;
  border-radius: 12px;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.file-card:hover { border-color: #2ec5b1; box-shadow: 0 2px 10px rgba(46, 197, 177, 0.14); }
.file-card-icon {
  flex: none;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #f4f6f9;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
}
.file-card-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.file-card-name {
  font-size: 13px;
  color: #2f3033;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-card-meta { font-size: 11px; color: #a6adbd; }
.user-bubble {
  white-space: pre-wrap;
  background: #e8f8f5;
  border-radius: 14px 14px 4px 14px;
  padding: 11px 15px;
  font-size: 14px;
  line-height: 1.7;
  max-width: 100%;
}
.assistant-block { max-width: 100%; min-width: 0; flex: 1; }
.assistant-bubble {
  background: #f7f8fa;
  border-radius: 4px 14px 14px 14px;
  padding: 12px 16px;
  max-width: 100%;
}

.thinking { margin-bottom: 8px; }
.thinking-head {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: none;
  background: transparent;
  color: #818999;
  font-size: 12px;
  cursor: pointer;
  padding: 2px 0;
}
.thinking-icon { color: #2ec5b1; }
.thinking-chev { color: #b7bdc9; }
.thinking-body {
  margin-top: 6px;
  border-left: 2px solid #e6e9ed;
  padding: 2px 0 2px 12px;
}
.reasoning {
  margin: 0 0 8px;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 12.5px;
  line-height: 1.75;
  color: #818999;
}
.activity-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #4a5160;
  padding: 2px 0;
}
.activity-state { color: #2ec5b1; width: 12px; }
.activity-state.error { color: #e5484d; }
.activity-time { color: #b7bdc9; font-size: 11px; }

.error-banner {
  margin: 6px 0;
  background: #fef2f2;
  color: #b42318;
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.waiting {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #818999;
  font-size: 13px;
}
.waiting-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #2ec5b1;
  animation: pulse 1.1s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.9); }
  50% { opacity: 1; transform: scale(1.15); }
}
.cursor { color: #2ec5b1; animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }

.msg-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
  font-size: 12px;
  color: #b7bdc9;
}
.msg-time { font-size: 11px; color: #b7bdc9; }
.stick-btn {
  position: sticky;
  bottom: 8px;
  align-self: center;
  background: #fff;
  border: 1px solid #e6e9ed;
  border-radius: 999px;
  padding: 5px 12px;
  font-size: 12px;
  color: #4a5160;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(20, 24, 34, 0.1);
}

.composer {
  flex: none;
  border-top: 1px solid #e6e9ed;
  padding: 12px 24px 16px;
  background: #fff;
  position: relative;
}
.composer-hint { font-size: 11px; color: #a6adbd; margin-bottom: 6px; }
.input-box {
  border: 1px solid #e6e9ed;
  border-radius: 14px;
  padding: 10px 12px;
  background: #fff;
}
.input-box:focus-within { border-color: #2ec5b1; }
.input-box textarea {
  width: 100%;
  min-height: 42px;
  max-height: 160px;
  border: none;
  outline: none;
  resize: vertical;
  font-size: 14px;
  line-height: 1.6;
  background: transparent;
}
.input-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}
.controls-left { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.icon-btn {
  border: 1px solid #e6e9ed;
  background: #fff;
  border-radius: 8px;
  width: 30px;
  height: 30px;
  cursor: pointer;
  color: #4a5160;
}
.icon-btn:hover { border-color: #2ec5b1; color: #2ec5b1; }
.icon-btn:disabled { opacity: 0.5; cursor: default; }
.project-select { height: 30px; font-size: 12px; max-width: 170px; }

.ctx-wrap { position: relative; }
.ctx-pill {
  display: inline-flex;
  align-items: center;
  height: 30px;
  padding: 0 8px;
  border: 1px solid #e6e9ed;
  border-radius: 8px;
  font-size: 11px;
  color: #818999;
  cursor: default;
  white-space: nowrap;
}
.ctx-pill.ok { color: #1f9e8c; border-color: #bfeee7; }
.ctx-pill.warn { color: #b45309; border-color: #fde68a; }
.ctx-pill.danger { color: #e5484d; border-color: #fecaca; }
.ctx-panel {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  width: 260px;
  background: #fff;
  border: 1px solid #e6e9ed;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(20, 24, 34, 0.12);
  padding: 12px 14px;
  z-index: 45;
  font-size: 12px;
}
.ctx-head { font-weight: 600; margin-bottom: 8px; }
.ctx-bar { height: 6px; background: #f0f1f5; border-radius: 3px; overflow: hidden; margin-bottom: 10px; }
.ctx-fill { height: 100%; background: #2ec5b1; }
.ctx-row { display: flex; justify-content: space-between; padding: 2px 0; color: #4a5160; }

.send {
  flex: none;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: #2ec5b1;
  color: #fff;
  font-size: 16px;
  cursor: pointer;
}
.send.stop { background: #e5484d; font-size: 12px; }

.attach-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  background: #f4f6f9;
  border: 1px solid #e6e9ed;
  border-radius: 9px;
  padding: 5px 8px;
  max-width: 320px;
}
.chip-icon { font-size: 14px; }
.chip-body { display: flex; flex-direction: column; min-width: 0; }
.chip-name { font-size: 12px; color: #2f3033; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip-meta { font-size: 10px; color: #a6adbd; display: flex; gap: 6px; }
.chip-warn { color: #b45309; }
.chip-x { border: none; background: transparent; color: #a6adbd; cursor: pointer; font-size: 14px; padding: 0 2px; }

.file-hidden { display: none; }

.picker-mask { position: fixed; inset: 0; z-index: 40; }
.picker {
  position: absolute;
  bottom: calc(100% - 4px);
  left: 24px;
  width: min(440px, calc(100% - 48px));
  max-height: 420px;
  background: #fff;
  border: 1px solid #e6e9ed;
  border-radius: 12px;
  box-shadow: 0 12px 36px rgba(20, 24, 34, 0.14);
  z-index: 41;
  display: flex;
  flex-direction: column;
}
.picker-head { display: flex; gap: 8px; padding: 10px; border-bottom: 1px solid #eef0f4; }
.picker-search { flex: 1; height: 32px; }
.picker-body { overflow-y: auto; padding: 6px; }
.picker-label { font-size: 11px; color: #a6adbd; padding: 8px 8px 4px; }
.picker-item {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  border: none;
  background: transparent;
  border-radius: 8px;
  padding: 8px;
  text-align: left;
  cursor: pointer;
}
.picker-item:hover { background: #f7f8fa; }
.picker-item.picked { background: #e8f8f5; }
.picker-check { width: 14px; color: #2ec5b1; font-size: 12px; padding-top: 1px; }
.picker-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.picker-name { font-size: 13px; color: #2f3033; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.picker-meta { font-size: 11px; color: #a6adbd; }
.picker-empty a { display: block; margin-top: 6px; }

.confirm-mask {
  position: fixed;
  inset: 0;
  background: rgba(20, 24, 34, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 70;
  padding: 24px;
}
.confirm-card {
  width: min(560px, 100%);
  max-height: 80vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 14px;
  padding: 22px;
  box-shadow: 0 16px 48px rgba(20, 24, 34, 0.2);
}
.confirm-title { font-size: 15px; font-weight: 700; margin-bottom: 8px; }
.confirm-summary { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; }
.confirm-cause { margin-top: 4px; color: #818999; font-size: 12px; }
.confirm-effects { margin-top: 4px; color: #b45309; font-size: 12px; }
.confirm-params {
  margin-top: 12px;
  background: #f8f9fc;
  border-radius: 10px;
  padding: 8px 10px;
  max-height: 240px;
  overflow-y: auto;
}
.param-row { display: flex; gap: 10px; padding: 4px 0; font-size: 12px; }
.param-key { flex: none; width: 92px; color: #818999; }
.param-value { margin: 0; white-space: pre-wrap; word-break: break-all; font-family: ui-monospace, Menlo, monospace; }
.confirm-timer { margin-top: 10px; font-size: 11px; color: #b7bdc9; }
.confirm-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
</style>
