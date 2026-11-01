<template>
  <div class="chat-page">
    <!-- 左栏：会话列表（点开回续，新建开新会话） -->
    <aside class="sessions">
      <button class="new-session" @click="newSession">＋ 新建会话</button>
      <div class="session-scroll">
        <template v-for="g in groupedSessions" :key="g.label">
          <div class="group-label">{{ g.label }}</div>
          <div v-for="s in g.items" :key="s.agent_id" class="session-item"
               :class="{ active: s.agent_id === conversationId }" @click="openSession(s)">
            <span class="s-name">{{ s.name || s.agent_id.slice(0, 8) }}</span>
            <span class="s-count">{{ s.message_count > 0 ? s.message_count + ' 条' : '' }}</span>
          </div>
        </template>
        <div class="empty-sessions" v-if="sessions.length === 0">还没有会话</div>
      </div>
    </aside>

    <!-- 右侧：聊天流 + 底部输入 -->
    <section class="chat-main">
      <div class="messages" ref="msgsBox">
        <template v-if="messages.length === 0">
          <div class="hero">BioPilot 你的科研智能搭档</div>
          <div class="cap-bar">
            <button v-for="(c, i) in caps" :key="c.name" class="cap"
                    :class="{ active: i === curCap }" @click="fillExample(c)">{{ c.name }}</button>
          </div>
          <button class="example" @click="fillExample(caps[curCap])">{{ caps[curCap].example }}</button>
        </template>
        <div v-for="(m, i) in messages" :key="i" class="row" :class="m.role">
          <pre class="bubble">{{ m.text }}</pre>
        </div>
      </div>

      <div class="composer">
        <textarea v-model="input" :placeholder="placeholder"
                  @keydown.enter.exact.prevent="send"></textarea>
        <div class="foot">
          <select v-if="models.length > 1" v-model="selectedModel" class="model-select" @change="selectModel">
            <option v-for="m in models" :key="m.name" :value="m.name">{{ m.name }}</option>
          </select>
          <span class="hint">Enter 发送 · Shift+Enter 换行 · 产物经安全确认后落库</span>
          <button class="send" :disabled="busy" @click="send">{{ busy ? '…' : '发送' }}</button>
        </div>
      </div>
    </section>

    <!-- 确认弹框：唯一确认决策点的前端半边——批准/拒绝由用户点选，300 秒不选服务端自动拒绝 -->
    <div v-if="pendingConfirm" class="confirm-mask">
      <div class="confirm-card">
        <div class="confirm-title">安全确认</div>
        <pre class="confirm-body">{{ pendingConfirm.summary || pendingConfirm.tool_name || '本次操作需要你的确认' }}</pre>
        <div class="confirm-actions">
          <button class="reject" @click="answerConfirm(false)">拒绝</button>
          <button class="ok" @click="answerConfirm(true)">批准</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// 对话主界面：左侧会话列表（点开经 /chat/history 回放），右侧聊天流 +
// 底部输入。confirm 帧挂起等用户裁决后回传 /chat/confirm；300 秒无操作
// 由服务端按拒绝处理（计时不在此处）。会话级模型切换下一 run 生效。
import { ref, computed, onMounted, nextTick } from 'vue'
import http from '../api/auth'

const caps = [
  { name: '生信分析', example: '示例：帮我整理单细胞 QC 的标准流程要点' },
  { name: '文献解析', example: '示例：帮我总结一篇论文的核心观点与图表结论' },
  { name: '知识解读', example: '示例：什么是单细胞测序技术？' },
  { name: '文档写作', example: '示例：帮我写一份空间组学的综述大纲' },
  { name: '平台搭建', example: '示例：帮我搭一个数据分析工具的静态展示页' },
]
const curCap = ref(0)
const input = ref('')
const busy = ref(false)
const messages = ref([])
const sessions = ref([])
const placeholder = '给 BioPilot 发送消息…（Enter 发送，Shift+Enter 换行）'
const pendingConfirm = ref(null)
const msgsBox = ref(null)

// 会话标识：默认开新会话；点左栏条目切到既有会话（历史经 /chat/history 回放）
let conversationId = crypto.randomUUID()

// 多模型选择：清单不含 key；切换只写会话偏好，下一 run 生效
const models = ref([])
const selectedModel = ref('')

onMounted(() => {
  loadSessions()
  loadModels()
})

const groupedSessions = computed(() => {
  const groups = [{ label: '今天', items: [] }, { label: '昨天', items: [] }, { label: '更早', items: [] }]
  const dayStart = new Date(); dayStart.setHours(0, 0, 0, 0)
  const yStart = new Date(dayStart); yStart.setDate(yStart.getDate() - 1)
  for (const s of sessions.value) {
    const t = new Date(s.created_at)
    if (t >= dayStart) groups[0].items.push(s)
    else if (t >= yStart) groups[1].items.push(s)
    else groups[2].items.push(s)
  }
  return groups.filter(g => g.items.length > 0)
})

async function loadSessions() {
  try {
    const { data } = await http.get('/sessions', { params: { limit: 100 } })
    sessions.value = data.data || []
  } catch { /* 列表拿不到就保持空态 */ }
}

async function loadModels() {
  try {
    const { data } = await http.get('/agent/models')
    models.value = data.models || []
    selectedModel.value = data.selected || data.models?.[0]?.name || ''
  } catch { /* 清单拿不到就不显示选择器（单模型部署） */ }
}

async function selectModel() {
  await http.post('/agent/models/select', { name: selectedModel.value })
}

function newSession() {
  if (busy.value) return
  conversationId = crypto.randomUUID()
  messages.value = []
  pendingConfirm.value = null
}

async function openSession(s) {
  if (busy.value || s.agent_id === conversationId) return
  conversationId = s.agent_id
  pendingConfirm.value = null
  try {
    const { data } = await http.get('/agent/chat/history', {
      params: { conversationId: s.agent_id },
    })
    messages.value = (data.messages || []).map(m => ({ role: m.role, text: m.content }))
  } catch {
    messages.value = []
  }
  await nextTick()
  scrollBottom()
}

function fillExample(c) {
  input.value = c.example.replace(/^示例：/, '')
  curCap.value = caps.indexOf(c)
}

function scrollBottom() {
  if (msgsBox.value) msgsBox.value.scrollTop = msgsBox.value.scrollHeight
}

async function send() {
  if (!input.value.trim() || busy.value) return
  const task = input.value
  input.value = ''
  messages.value.push({ role: 'user', text: task })
  const reply = { role: 'assistant', text: '' }
  messages.value.push(reply)
  busy.value = true
  await nextTick(); scrollBottom()
  try {
    const resp = await fetch('/api/agent/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'satoken': localStorage.getItem('biopilot_token') || '',
        'X-Conversation-Id': conversationId,
      },
      body: JSON.stringify({ task, conversation_id: conversationId }),
    })
    if (resp.status === 401) {
      // 登录态失效（服务重启/过期）：跳登录页重新拿 token
      reply.text = '登录已失效，正在跳转登录页…'
      setTimeout(() => { window.location.href = '/login' }, 800)
      return
    }
    if (!resp.ok || !resp.body) {
      // 非 200：读 JSON 错误体给用户看（429 配额/422 缺参/装配失败在此分支）
      let detail = `HTTP ${resp.status}`
      try {
        const data = await resp.json()
        detail = data.msg || (typeof data.detail === 'string' ? data.detail : detail)
      } catch { /* 非 JSON 响应体保持状态码提示 */ }
      reply.text = `对话失败：${detail}`
      return
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const frame = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        for (const line of frame.split('\n')) {
          if (!line.startsWith('data: ')) continue
          const evt = JSON.parse(line.slice(6))
          if (evt.type === 'token') { reply.text += evt.text; scrollBottom() }
          else if (evt.type === 'done' && evt.text) { reply.text = evt.text; scrollBottom() }
          else if (evt.type === 'error') reply.text = `出错：${evt.text}`
          else if (evt.type === 'confirm') {
            // 挂起弹框等用户裁决；流保持打开，回答在批准后继续下行
            pendingConfirm.value = evt
            reply.text = `待确认：${evt.summary || evt.tool_name || '危险操作'}`
          }
        }
      }
    }
  } catch (e) {
    // 已流式输出的内容保留（断网丢掉全部回答不可接受），只追加中断原因
    reply.text = reply.text ? `${reply.text}\n\n[连接中断：${e.message}]` : `对话失败：${e.message}`
  } finally {
    busy.value = false
    loadSessions()   // 新会话/新标题进左栏
    await nextTick(); scrollBottom()
  }
}

// 确认回传：批准=true / 拒绝=false；服务端计时，超时未回传视为拒绝
async function answerConfirm(approved) {
  const evt = pendingConfirm.value
  pendingConfirm.value = null
  if (!evt) return
  const last = messages.value[messages.value.length - 1]
  if (last && last.text?.startsWith('待确认：')) {
    last.text = approved ? '已批准，继续执行…' : '已拒绝'
  }
  await fetch('/api/agent/chat/confirm', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'satoken': localStorage.getItem('biopilot_token') || '',
    },
    body: JSON.stringify({ req_id: evt.req_id, conversation_id: conversationId, approved }),
  })
}
</script>

<style scoped>
.chat-page { display: flex; height: 100vh; overflow: hidden; }
/* 左栏会话列表 */
.sessions { width: 230px; flex: none; border-right: 1px solid #e6e9ed; padding: 14px 10px; display: flex; flex-direction: column; gap: 6px; background: #fafbfc; }
.new-session { border: 1px solid #e6e9ed; background: #fff; border-radius: 10px; padding: 10px; cursor: pointer; font-size: 13px; }
.new-session:hover { border-color: #2ec5b1; color: #2ec5b1; }
.session-scroll { overflow-y: auto; margin-top: 4px; }
.group-label { font-size: 11px; color: #a6adbd; margin: 10px 4px 4px; }
.session-item { padding: 9px 10px; border-radius: 8px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 6px; }
.session-item:hover { background: #f0f1f5; }
.session-item.active { background: #e8f8f5; }
.session-item.active .s-name { color: #2ec5b1; font-weight: 600; }
.s-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.s-count { font-size: 11px; color: #a6adbd; flex: none; }
.empty-sessions { font-size: 12px; color: #a6adbd; text-align: center; padding: 24px 0; }

/* 右侧聊天区：消息滚动区 + 底部输入 */
.chat-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.messages { flex: 1; overflow-y: auto; padding: 28px 32px; display: flex; flex-direction: column; gap: 14px; }
.hero { font-size: 32px; font-weight: 700; text-align: center; margin-top: 8vh; }
.cap-bar { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; margin: 20px 0 12px; }
.cap { background: #f8f9fc; border: none; border-radius: 8px; padding: 8px 12px; cursor: pointer; font-size: 13px; }
.cap.active { background: #2ec5b1; color: #fff; }
.example { display: block; margin: 0 auto; border: 1px solid #e6e9ed; border-radius: 10px; padding: 10px 16px; background: #fff; cursor: pointer; font-size: 13px; color: #818999; }
.row { display: flex; }
.row.user { justify-content: flex-end; }
.bubble { white-space: pre-wrap; font-family: inherit; margin: 0; padding: 12px 14px; border-radius: 12px; font-size: 14px; line-height: 1.65; max-width: 76%; }
.row.user .bubble { background: #e8f8f5; }
.row.assistant .bubble { background: #f5f6f9; }
.composer { border-top: 1px solid #e6e9ed; padding: 14px 20px; background: #fff; }
.composer textarea { width: 100%; min-height: 56px; max-height: 160px; border: 1px solid #e6e9ed; border-radius: 12px; padding: 10px 12px; font-size: 14px; outline: none; resize: vertical; box-sizing: border-box; }
.foot { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; gap: 10px; }
.hint { font-size: 12px; color: #a6adbd; }
.send { background: #2ec5b1; color: #fff; border: none; border-radius: 50%; width: 36px; height: 36px; cursor: pointer; flex: none; }
.send:disabled { opacity: .6; cursor: default; }
.model-select { border: 1px solid #e6e9ed; border-radius: 8px; padding: 4px 8px; font-size: 12px; color: #4a5160; background: #fff; }

/* 确认弹框 */
.confirm-mask { position: fixed; inset: 0; background: rgba(20, 24, 34, .45); display: flex; align-items: center; justify-content: center; z-index: 50; }
.confirm-card { background: #fff; border-radius: 14px; padding: 20px 22px; width: min(520px, 90vw); box-shadow: 0 12px 40px rgba(0,0,0,.18); }
.confirm-title { font-weight: 700; margin-bottom: 10px; }
.confirm-body { white-space: pre-wrap; font-family: inherit; background: #f8f9fc; border-radius: 10px; padding: 12px; font-size: 13px; margin: 0 0 14px; }
.confirm-actions { display: flex; gap: 10px; justify-content: flex-end; }
.confirm-actions button { border: none; border-radius: 8px; padding: 8px 18px; cursor: pointer; font-size: 13px; }
.confirm-actions .ok { background: #2ec5b1; color: #fff; }
.confirm-actions .reject { background: #f1f3f7; color: #4a5160; }
</style>
