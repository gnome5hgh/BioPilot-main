<template>
  <div class="chat">
    <div class="hero">BioPilot 你的科研智能搭档</div>
    <div class="cap-bar">
      <button v-for="(c, i) in caps" :key="c.name" class="cap" :class="{ active: i === curCap }" @click="curCap = i">
        {{ c.name }}
      </button>
    </div>
    <button class="example" @click="fillExample">{{ caps[curCap].example }}</button>
    <div class="input-card">
      <textarea v-model="input" :placeholder="placeholder" @keydown.enter.exact.prevent="send"></textarea>
      <div class="foot">
        <select v-if="models.length > 1" v-model="selectedModel" class="model-select" @change="selectModel">
          <option v-for="m in models" :key="m.name" :value="m.name">{{ m.name }}</option>
        </select>
        <span class="hint">Enter 发送 · 产物经安全确认后落库</span>
        <button class="send" :disabled="busy" @click="send">{{ busy ? '…' : '发送' }}</button>
      </div>
    </div>
    <div class="messages">
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <pre>{{ m.text }}</pre>
      </div>
    </div>
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
// 对话闭环：SSE 经 SpringBoot 转发到 Python 适配层。confirm 帧挂起等待用户
// 点选后回传 /chat/confirm；300 秒无操作由服务端按拒绝处理（计时不在此处）。
import { ref, onMounted } from 'vue'
import http from '../api/auth'

// 会话标识：本次进入页面生成一个（跨用户撞名面由 uuid 消除）
const conversationId = crypto.randomUUID()

// 多模型选择：清单不含 key；切换只写会话偏好，下一 run 生效
const models = ref([])
const selectedModel = ref('')
onMounted(async () => {
  try {
    const { data } = await http.get('/agent/models')
    models.value = data.models || []
    selectedModel.value = data.selected || data.models?.[0]?.name || ''
  } catch { /* 清单拿不到就不显示选择器（单模型部署） */ }
})

async function selectModel() {
  await http.post('/agent/models/select', { name: selectedModel.value })
}

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
const placeholder = '发送消息…（Enter 发送，Shift+Enter 换行）'
const pendingConfirm = ref(null)

function fillExample() {
  input.value = caps.value[curCap.value].example.replace(/^示例：/, '')
}

async function send() {
  if (!input.value.trim() || busy.value) return
  const task = input.value
  input.value = ''
  messages.value.push({ role: 'user', text: task })
  const reply = { role: 'assistant', text: '' }
  messages.value.push(reply)
  busy.value = true
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
      // 登录态失效（服务重启/过期）：跳登录页重新拿 token，别只报错让人卡在原地
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
          if (evt.type === 'token') reply.text += evt.text
          else if (evt.type === 'done' && evt.text) reply.text = evt.text
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
.chat { padding: 40px 24px; max-width: 900px; margin: 0 auto; }
.hero { font-size: 34px; font-weight: 700; }
.cap-bar { display: flex; gap: 8px; margin: 24px 0 12px; flex-wrap: wrap; }
.cap { background: #f8f9fc; border: none; border-radius: 8px; padding: 8px 12px; cursor: pointer; font-size: 13px; }
.cap.active { background: #2ec5b1; color: #fff; }
.example { display: block; width: 100%; text-align: left; border: 1px solid #e6e9ed; border-radius: 10px; padding: 11px 14px; background: #fff; cursor: pointer; font-size: 13px; color: #818999; }
.input-card { border: 1px solid #e6e9ed; border-radius: 14px; padding: 12px 14px; margin-top: 16px; }
textarea { width: 100%; min-height: 54px; border: none; resize: none; font-size: 14px; outline: none; }
.foot { display: flex; justify-content: space-between; align-items: center; }
.hint { font-size: 12px; color: #a6adbd; }
.send { background: #2ec5b1; color: #fff; border: none; border-radius: 50%; width: 34px; height: 34px; cursor: pointer; }
.messages { margin-top: 24px; display: flex; flex-direction: column; gap: 12px; }
.msg pre { white-space: pre-wrap; font-family: inherit; margin: 0; padding: 12px 14px; border-radius: 10px; font-size: 14px; }
.msg.user pre { background: #e8f8f5; }
.confirm-mask { position: fixed; inset: 0; background: rgba(20, 24, 34, .45); display: flex; align-items: center; justify-content: center; z-index: 50; }
.confirm-card { background: #fff; border-radius: 14px; padding: 20px 22px; width: min(520px, 90vw); box-shadow: 0 12px 40px rgba(0,0,0,.18); }
.confirm-title { font-weight: 700; margin-bottom: 10px; }
.confirm-body { white-space: pre-wrap; font-family: inherit; background: #f8f9fc; border-radius: 10px; padding: 12px; font-size: 13px; margin: 0 0 14px; }
.confirm-actions { display: flex; gap: 10px; justify-content: flex-end; }
.confirm-actions button { border: none; border-radius: 8px; padding: 8px 18px; cursor: pointer; font-size: 13px; }
.confirm-actions .ok { background: #2ec5b1; color: #fff; }
.confirm-actions .reject { background: #f1f3f7; color: #4a5160; }
.model-select { border: 1px solid #e6e9ed; border-radius: 8px; padding: 4px 8px; font-size: 12px; color: #4a5160; background: #fff; }
</style>
