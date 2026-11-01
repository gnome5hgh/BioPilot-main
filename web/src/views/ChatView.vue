<template>
  <div class="chat-page">
    <!-- 左栏：项目 + 会话列表 -->
    <aside class="sessions">
      <button class="new-session" @click="newSession">＋ 新建会话</button>
      <div class="session-scroll">
        <!-- 项目区：项目可选中（新会话归属它），展开显示其下会话 -->
        <div class="group-label row-between">
          <span>项目</span>
          <button class="mini-add" title="新建项目" @click="showProjectInput = !showProjectInput">＋</button>
        </div>
        <div class="project-input" v-if="showProjectInput">
          <input v-model="newProjectName" placeholder="项目名称，回车确认"
                 @keydown.enter.exact.prevent="createProject" />
        </div>
        <div v-for="p in projects" :key="p.projectId" class="project-block">
          <div class="project-item" :class="{ selected: p.projectId === currentProject }"
               @click="selectProject(p)">
            <span class="p-name">📁 {{ p.name }}</span>
            <span class="item-menu" :title="'在「' + p.name + '」下新建会话'"
                  @click.stop="newSessionFor(p.projectId)">⊕</span>
          </div>
          <template v-if="expanded.has(p.projectId)">
            <div v-for="s in sessionsOf(p.projectId)" :key="s.agent_id"
                 class="session-item sub" :class="{ active: s.agent_id === conversationId }"
                 @click="openSession(s)">
              <span class="s-name">{{ s.name || s.agent_id.slice(0, 8) }}</span>
              <span class="s-time">{{ relTime(s.created_at) }}</span>
              <span class="item-menu" @click.stop="menuFor = menuFor === s.agent_id ? null : (confirmDelete = null, s.agent_id)">⋯</span>
              <div v-if="menuFor === s.agent_id" class="menu-pop" @click.stop>
                <button class="menu-item danger" @click="deleteSession(s)">
                  {{ confirmDelete === s.agent_id ? '再点一次确认删除' : '删除会话' }}
                </button>
              </div>
            </div>
            <div class="empty-sessions" v-if="sessionsOf(p.projectId).length === 0">暂无会话</div>
          </template>
        </div>

        <!-- 未分组会话（按日期） -->
        <div class="group-label">会话</div>
        <template v-for="g in ungroupedGroups" :key="g.label">
          <div class="sub-label">{{ g.label }}</div>
          <div v-for="s in g.items" :key="s.agent_id"
               class="session-item" :class="{ active: s.agent_id === conversationId }"
               @click="openSession(s)">
            <span class="s-name">{{ s.name || s.agent_id.slice(0, 8) }}</span>
            <span class="s-time">{{ relTime(s.created_at) }}</span>
            <span class="item-menu" @click.stop="menuFor = menuFor === s.agent_id ? null : (confirmDelete = null, s.agent_id)">⋯</span>
            <div v-if="menuFor === s.agent_id" class="menu-pop" @click.stop>
              <button class="menu-item danger" @click="deleteSession(s)">
                {{ confirmDelete === s.agent_id ? '再点一次确认删除' : '删除会话' }}
              </button>
            </div>
          </div>
        </template>
        <div class="empty-sessions" v-if="sessions.length === 0 && projects.length === 0">还没有会话</div>
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
        <div class="project-hint" v-if="currentProjectName">
          📁 {{ currentProjectName }} · 本会话的消息将归入该项目
        </div>
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
// 对话主界面：左侧项目 + 会话列表（点会话经 /chat/history 回放；⋯ 菜单删除），
// 右侧聊天流 + 底部输入。选中项目后，新会话的第一条消息会把会话归入该项目。
// confirm 帧挂起等用户裁决后回传 /chat/confirm；300 秒无操作由服务端按拒绝处理。
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
const projects = ref([])
const currentProject = ref(null)     // 新会话归属的项目（null = 未分组）
const expanded = ref(new Set())      // 展开的项目集合
const menuFor = ref(null)            // 当前打开 ⋯ 菜单的会话 id
const confirmDelete = ref(null)      // 两步删除：第一次点记下会话 id，再点执行
const showProjectInput = ref(false)
const newProjectName = ref('')
const placeholder = '给 BioPilot 发送消息…（Enter 发送，Shift+Enter 换行）'
const pendingConfirm = ref(null)
const msgsBox = ref(null)

// 会话标识：默认开新会话；点左栏条目切到既有会话（历史经 /chat/history 回放）
let conversationId = crypto.randomUUID()

// 多模型选择：清单不含 key；切换只写会话偏好，下一 run 生效
const models = ref([])
const selectedModel = ref('')

const currentProjectName = computed(() =>
  projects.value.find(p => p.projectId === currentProject.value)?.name || '')

onMounted(() => {
  loadSessions()
  loadProjects()
  loadModels()
})

function dateGroup(t) {
  const dayStart = new Date(); dayStart.setHours(0, 0, 0, 0)
  const yStart = new Date(dayStart); yStart.setDate(yStart.getDate() - 1)
  if (t >= dayStart) return '今天'
  if (t >= yStart) return '昨天'
  return '更早'
}

const ungroupedGroups = computed(() => {
  const groups = {}
  for (const s of sessions.value) {
    if (s.project_id) continue
    const label = dateGroup(new Date(s.created_at))
    ;(groups[label] = groups[label] || { label, items: [] }).items.push(s)
  }
  const order = ['今天', '昨天', '更早']
  return order.map(l => groups[l]).filter(Boolean)
})

async function loadSessions() {
  try {
    const { data } = await http.get('/sessions', { params: { limit: 200 } })
    const locals = sessions.value.filter(s => s.localOnly
      && !(data.data || []).some(r => r.agent_id === s.agent_id))
    sessions.value = [...locals, ...(data.data || [])]
  } catch { /* 列表拿不到就保持空态 */ }
}

async function loadProjects() {
  try {
    const { data } = await http.get('/project')
    projects.value = data.data || []
  } catch { /* 拿不到就空态 */ }
}

async function createProject() {
  const name = newProjectName.value.trim()
  if (!name) return
  try {
    const { data } = await http.post('/project', { name })
    showProjectInput.value = false
    newProjectName.value = ''
    await loadProjects()
    currentProject.value = data.data?.projectId || null
    expanded.value = new Set([...expanded.value, currentProject.value])
  } catch (e) {
    window.alert(e?.response?.data?.msg || '新建项目失败')
  }
}

function selectProject(p) {
  currentProject.value = p.projectId
  const next = new Set(expanded.value)
  next.add(p.projectId)
  expanded.value = next
}

function sessionsOf(pid) {
  return sessions.value.filter(s => s.project_id === pid)
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

function resetChat() {
  messages.value = []
  pendingConfirm.value = null
  menuFor.value = null
  confirmDelete.value = null
}

function newSession() {
  if (busy.value) return
  conversationId = crypto.randomUUID()
  currentProject.value = null
  resetChat()
}

// 在指定项目下开新会话：先在列表里放一个本地占位条目（首条消息落库后
// 被服务端数据替换，标题由首条任务自动生成）
function newSessionFor(projectId) {
  if (busy.value) return
  conversationId = crypto.randomUUID()
  currentProject.value = projectId
  resetChat()
  const next = new Set(expanded.value); next.add(projectId)
  expanded.value = next
  if (!sessions.value.some(s => s.agent_id === conversationId)) {
    sessions.value.unshift({
      agent_id: conversationId, name: "新会话", project_id: projectId,
      created_at: new Date().toISOString(), localOnly: true,
    })
  }
  input.value = ""
}

// 相对时间标签（与参考图一致：刚刚 / N 天前）
function relTime(iso) {
  if (!iso) return ""
  const t = new Date(iso)
  if (Number.isNaN(t.getTime())) return ""
  const day = 24 * 3600 * 1000
  const startToday = new Date(); startToday.setHours(0, 0, 0, 0)
  if (t >= startToday) return "刚刚"
  const days = Math.floor((startToday - t) / day) + 1
  if (days === 1) return "昨天"
  return `${days}天`
}

async function openSession(s) {
  if (busy.value || s.agent_id === conversationId) return
  conversationId = s.agent_id
  pendingConfirm.value = null
  menuFor.value = null
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

async function deleteSession(s) {
  // 两步确认（不弹原生框）：第一次点标记，再点执行
  if (confirmDelete.value !== s.agent_id) {
    confirmDelete.value = s.agent_id
    return
  }
  confirmDelete.value = null
  menuFor.value = null
  try {
    await http.delete('/agent/chat/session', { params: { conversationId: s.agent_id } })
    if (s.agent_id === conversationId) newSession()
    await loadSessions()
  } catch (e) {
    window.alert(e?.response?.data?.msg || '删除失败')
  }
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
      body: JSON.stringify({
        task, conversation_id: conversationId, project_id: currentProject.value,
      }),
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
    loadSessions()   // 新会话/新标题/项目归属进左栏
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
/* 左栏：项目 + 会话 */
.sessions { width: 240px; flex: none; border-right: 1px solid #e6e9ed; padding: 14px 10px; display: flex; flex-direction: column; gap: 6px; background: #fafbfc; }
.new-session { border: 1px solid #e6e9ed; background: #fff; border-radius: 10px; padding: 10px; cursor: pointer; font-size: 13px; }
.new-session:hover { border-color: #2ec5b1; color: #2ec5b1; }
.session-scroll { overflow-y: auto; margin-top: 4px; }
.group-label { font-size: 11px; color: #a6adbd; margin: 10px 4px 4px; }
.row-between { display: flex; justify-content: space-between; align-items: center; }
.mini-add { border: none; background: transparent; cursor: pointer; color: #2ec5b1; font-size: 13px; padding: 0 4px; }
.project-input { margin: 2px 0 6px; }
.project-input input { width: 100%; box-sizing: border-box; border: 1px solid #2ec5b1; border-radius: 8px; padding: 7px 9px; font-size: 12px; outline: none; }
.sub-label { font-size: 11px; color: #b7bdc9; margin: 6px 4px 2px 18px; }
.project-item { padding: 8px 10px; border-radius: 8px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
.project-item:hover { background: #f0f1f5; }
.project-item.selected { background: #e8f8f5; }
.project-item.selected .p-name { color: #2ec5b1; font-weight: 600; }
.p-count { font-size: 11px; color: #a6adbd; }
.session-item { position: relative; padding: 9px 10px; border-radius: 8px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 6px; }
.session-item.sub { margin-left: 16px; }
.session-item:hover { background: #f0f1f5; }
.session-item.active { background: #e8f8f5; }
.session-item.active .s-name { color: #2ec5b1; font-weight: 600; }
.s-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.s-count { font-size: 11px; color: #a6adbd; flex: none; }
.s-time { font-size: 11px; color: #a6adbd; flex: none; }
.p-count { font-size: 11px; color: #a6adbd; flex: none; }
.item-menu { flex: none; font-size: 13px; color: #a6adbd; cursor: pointer; padding: 0 4px; border-radius: 4px; visibility: hidden; }
.project-item .item-menu { margin-left: auto; visibility: visible; font-size: 15px; }
.session-item:hover .item-menu { visibility: visible; }
.menu-pop { position: absolute; right: 6px; top: 30px; background: #fff; border: 1px solid #e6e9ed; border-radius: 8px; box-shadow: 0 6px 20px rgba(0,0,0,.12); z-index: 20; min-width: 96px; }
.menu-item { display: block; width: 100%; border: none; background: transparent; text-align: left; padding: 8px 12px; font-size: 12px; cursor: pointer; }
.menu-item.danger { color: #e5484d; }
.menu-item:hover { background: #f8f9fc; }
.empty-sessions { font-size: 12px; color: #a6adbd; text-align: center; padding: 16px 0; }

/* 右侧聊天区 */
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
.project-hint { font-size: 12px; color: #2ec5b1; margin-bottom: 8px; }
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
