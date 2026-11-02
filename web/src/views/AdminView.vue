<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">管理端</h2>
        <p class="page-sub">用户、会话与审计；危险操作统一二次确认。</p>
      </div>
      <div class="toolbar">
        <button class="btn" @click="load">刷新</button>
      </div>
    </div>

    <div class="seg main-tabs">
      <button :class="{ active: tab === 'users' }" @click="tab = 'users'">用户管理</button>
      <button :class="{ active: tab === 'sessions' }" @click="tab = 'sessions'">会话总览</button>
      <button :class="{ active: tab === 'audit' }" @click="tab = 'audit'">审计日志</button>
    </div>

    <!-- 用户管理 -->
    <template v-if="tab === 'users'">
      <div class="toolbar filter-row">
        <input v-model="userQuery" class="input" placeholder="搜索用户名 / 昵称" />
        <span class="faint">共 {{ users.length }} 个账号</span>
      </div>
      <table class="table">
        <thead>
          <tr><th>用户名</th><th>昵称</th><th>角色</th><th>状态</th><th>创建时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="user in filteredUsers" :key="user.userId">
            <td>
              {{ user.userName }}
              <span v-if="isSelf(user)" class="badge badge-info">我</span>
            </td>
            <td>{{ user.nickName || '—' }}</td>
            <td>{{ user.role }}</td>
            <td>
              <span class="badge" :class="user.status === '0' ? 'badge-brand' : 'badge-danger'">
                {{ user.status === '0' ? '正常' : '停用' }}
              </span>
            </td>
            <td>{{ user.createTime ? fmtDateTime(user.createTime) : '—' }}</td>
            <td class="actions">
              <button class="btn btn-sm" :disabled="isSelf(user)" @click="toggleStatus(user)">
                {{ user.status === '0' ? '停用' : '启用' }}
              </button>
              <button class="btn btn-sm" @click="openReset(user)">重置密码</button>
              <button class="btn btn-sm" :disabled="isSelf(user)" @click="changeRole(user)">
                {{ user.role === 'ADMIN' ? '降为 USER' : '升为 ADMIN' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!filteredUsers.length" class="empty">没有匹配的账号。</div>
    </template>

    <!-- 会话总览 -->
    <template v-else-if="tab === 'sessions'">
      <div class="toolbar filter-row">
        <input v-model="sessionQuery" class="input" placeholder="搜索会话名" />
        <select v-model="sessionUser" class="select">
          <option value="">全部用户</option>
          <option v-for="user in users" :key="user.userId" :value="String(user.userId)">
            {{ user.nickName || user.userName }}
          </option>
        </select>
        <label class="check"><input type="checkbox" v-model="hideEmpty" /> 隐藏 0 消息会话</label>
      </div>
      <table class="table">
        <thead><tr><th>会话</th><th>归属用户</th><th>消息数</th><th>创建时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="session in filteredSessions" :key="session.agent_id">
            <td>{{ session.name || session.agent_id.slice(0, 8) }}</td>
            <td>{{ userName(session.user_id) }}</td>
            <td>{{ session.message_count }}</td>
            <td>{{ fmtDateTime(session.created_at) }}</td>
            <td><button class="btn btn-sm" @click="showDetail('会话详情', session)">详情</button></td>
          </tr>
        </tbody>
      </table>
      <div v-if="!filteredSessions.length" class="empty">没有匹配的会话。</div>
    </template>

    <!-- 审计日志 -->
    <template v-else>
      <div class="seg sub-tabs">
        <button :class="{ active: auditSource === 'events' }" @click="auditSource = 'events'">操作审计</button>
        <button :class="{ active: auditSource === 'logins' }" @click="auditSource = 'logins'">登录日志</button>
      </div>

      <template v-if="auditSource === 'events'">
        <div class="toolbar filter-row">
          <select v-model="auditEvent" class="select">
            <option value="">全部事件</option>
            <option v-for="value in eventTypes" :key="value" :value="value">{{ value }}</option>
          </select>
          <select v-model="auditRisk" class="select">
            <option value="">全部风险</option>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
            <option value="critical">critical</option>
          </select>
          <select v-model="auditDecision" class="select">
            <option value="">全部决策</option>
            <option v-for="value in decisions" :key="value" :value="value">{{ value }}</option>
          </select>
          <input v-model="auditUser" class="input" placeholder="按用户筛选" />
          <button class="btn" @click="exportEvents">导出 CSV</button>
        </div>
        <table class="table">
          <thead>
            <tr><th>时间</th><th>用户</th><th>事件</th><th>工具/角色</th><th>风险</th><th>决策</th><th>结果</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="event in visibleEvents" :key="event.id">
              <td>{{ fmtDateTime(event.started_at) }}</td>
              <td>{{ userName(event.user_id) }}</td>
              <td>{{ event.event_type }}</td>
              <td>{{ event.tool_name || event.agent_type || '—' }}</td>
              <td>{{ event.risk_level || '—' }}</td>
              <td>{{ event.policy_decision || event.approval_outcome || '—' }}</td>
              <td>{{ event.result_status || '—' }}</td>
              <td><button class="btn btn-sm" @click="showDetail('审计详情', event)">详情</button></td>
            </tr>
          </tbody>
        </table>
        <div v-if="!visibleEvents.length" class="empty">没有匹配的审计事件。</div>
        <div v-else-if="filteredEvents.length > auditLimit" class="more-row">
          <button class="btn btn-sm" @click="auditLimit += 100">
            显示更多（已显示 {{ visibleEvents.length }} / {{ filteredEvents.length }}）
          </button>
        </div>
      </template>

      <template v-else>
        <table class="table">
          <thead><tr><th>用户名</th><th>结果</th><th>IP</th><th>时间</th></tr></thead>
          <tbody>
            <tr v-for="log in logins" :key="log.id">
              <td>{{ log.userName }}</td>
              <td>{{ log.outcome }}</td>
              <td>{{ log.ip }}</td>
              <td>{{ fmtDateTime(log.createTime) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="!logins.length" class="empty">暂无登录记录。</div>
      </template>
    </template>

    <!-- 详情抽屉 -->
    <div v-if="detail.open" class="modal-mask" @click.self="detail.open = false">
      <div class="modal-card">
        <div class="modal-head">
          <span class="modal-title">{{ detail.title }}</span>
          <button class="btn btn-sm" @click="detail.open = false">关闭</button>
        </div>
        <div class="detail-body">
          <div v-for="row in detail.rows" :key="row.key" class="detail-row">
            <span class="detail-key">{{ row.key }}</span>
            <pre class="detail-value">{{ row.value }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- 重置密码 -->
    <div v-if="reset.open" class="modal-mask" @click.self="reset.open = false">
      <div class="modal-card small">
        <div class="modal-head">
          <span class="modal-title">重置 {{ reset.user?.userName }} 的密码</span>
          <button class="btn btn-sm" @click="reset.open = false">取消</button>
        </div>
        <div class="reset-body">
          <input v-model="reset.password" type="password" class="input" placeholder="新密码（至少 8 位）" />
          <div class="faint">重置后该用户需要重新登录；不会把密码显示或记录在任何地方。</div>
          <button class="btn btn-primary" :disabled="reset.password.length < 8 || reset.saving"
                  @click="submitReset">{{ reset.saving ? '提交中…' : '确认重置' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import http, { useAuthStore } from '../api/auth'
import { confirmDialog } from '../utils/confirm'
import { errText } from '../utils/errors'
import { toast } from '../utils/toast'
import { fmtDateTime } from '../utils/time'

const auth = useAuthStore()
const tab = ref('users')
const users = ref([])
const sessions = ref([])
const auditEvents = ref([])
const logins = ref([])
const auditSource = ref('events')
const userQuery = ref('')
const sessionQuery = ref('')
const sessionUser = ref('')
const hideEmpty = ref(false)
const auditEvent = ref('')
const auditRisk = ref('')
const auditDecision = ref('')
const auditUser = ref('')
const auditLimit = ref(100)

const detail = reactive({ open: false, title: '', rows: [] })
const reset = reactive({ open: false, user: null, password: '', saving: false })

const filteredUsers = computed(() => {
  const text = userQuery.value.trim().toLowerCase()
  if (!text) return users.value
  return users.value.filter((user) =>
    user.userName.toLowerCase().includes(text)
    || (user.nickName || '').toLowerCase().includes(text))
})

const filteredSessions = computed(() => {
  const text = sessionQuery.value.trim().toLowerCase()
  return sessions.value.filter((session) => {
    if (hideEmpty.value && !session.message_count) return false
    if (sessionUser.value && String(session.user_id) !== sessionUser.value) return false
    if (!text) return true
    return (session.name || session.agent_id).toLowerCase().includes(text)
  })
})

const eventTypes = computed(() =>
  [...new Set(auditEvents.value.map((event) => event.event_type).filter(Boolean))].sort())

const decisions = computed(() =>
  [...new Set(auditEvents.value.map((event) =>
    event.policy_decision || event.approval_outcome).filter(Boolean))].sort())

const filteredEvents = computed(() => auditEvents.value.filter((event) => {
  if (auditEvent.value && event.event_type !== auditEvent.value) return false
  if (auditRisk.value && event.risk_level !== auditRisk.value) return false
  if (auditDecision.value
    && (event.policy_decision || event.approval_outcome) !== auditDecision.value) return false
  if (auditUser.value) {
    const text = auditUser.value.toLowerCase()
    const name = userName(event.user_id).toLowerCase()
    if (!name.includes(text) && !String(event.user_id).includes(text)) return false
  }
  return true
}))

const visibleEvents = computed(() => filteredEvents.value.slice(0, auditLimit.value))

onMounted(load)

async function load() {
  try {
    const [userResp, sessionResp, eventResp, loginResp] = await Promise.all([
      http.get('/admin/api/users'),
      http.get('/admin/api/sessions'),
      http.get('/admin/api/audit-events'),
      http.get('/admin/api/audit'),
    ])
    users.value = userResp.data.data || []
    sessions.value = sessionResp.data.data || []
    auditEvents.value = eventResp.data.data || []
    logins.value = loginResp.data.data || []
  } catch (error) {
    toast(errText(error, '管理数据读取失败'), 'error')
  }
}

function isSelf(user) {
  return String(user.userId) === String(auth.userId)
}

function userName(userId) {
  if (!userId) return '—'
  if (userId === 'local') return '本地/终端'
  const user = users.value.find((item) => String(item.userId) === String(userId))
  return user ? (user.nickName || user.userName) : String(userId)
}

async function toggleStatus(user) {
  const next = user.status === '0' ? '1' : '0'
  const ok = await confirmDialog({
    title: next === '1' ? '停用账号' : '启用账号',
    message: `${next === '1' ? '停用' : '启用'}「${user.userName}」？`,
    detail: next === '1' ? '停用后该账号无法登录，进行中的会话会被切断。' : '',
    confirmText: next === '1' ? '停用' : '启用',
    danger: next === '1',
  })
  if (!ok) return
  try {
    await http.post(`/admin/api/users/${user.userId}`, { status: next })
    toast(next === '1' ? '账号已停用' : '账号已启用', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '操作失败'), 'error')
  }
}

async function changeRole(user) {
  const next = user.role === 'ADMIN' ? 'USER' : 'ADMIN'
  const ok = await confirmDialog({
    title: '修改角色',
    message: `把「${user.userName}」改为 ${next}？`,
    detail: next === 'ADMIN' ? '管理员可以管理所有用户、会话与审计。' : '降级后该账号立即失去管理端权限。',
    confirmText: '确认修改',
    danger: next === 'USER',
  })
  if (!ok) return
  try {
    await http.post(`/admin/api/users/${user.userId}`, { role: next })
    toast('角色已更新', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '修改失败'), 'error')
  }
}

function openReset(user) {
  reset.open = true
  reset.user = user
  reset.password = ''
  reset.saving = false
}

async function submitReset() {
  if (!reset.user || reset.password.length < 8) return
  reset.saving = true
  try {
    await http.post(`/admin/api/users/${reset.user.userId}/reset-password`, {
      password: reset.password,
    })
    toast('密码已重置，请把新密码交给本人', 'success')
    reset.open = false
  } catch (error) {
    toast(errText(error, '重置失败'), 'error')
  } finally {
    reset.saving = false
  }
}

function showDetail(title, row) {
  detail.title = title
  detail.rows = Object.entries(row).map(([key, value]) => ({
    key,
    value: value === null || value === undefined
      ? '—'
      : (typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)),
  }))
  detail.open = true
}

function exportEvents() {
  const rows = filteredEvents.value
  if (!rows.length) {
    toast('没有可导出的审计事件', 'error')
    return
  }
  const columns = ['started_at', 'user_id', 'event_type', 'tool_name', 'agent_type',
    'risk_level', 'policy_decision', 'approval_outcome', 'result_status']
  const escape = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`
  const lines = [columns.join(',')]
  for (const row of rows) {
    lines.push(columns.map((column) => escape(row[column])).join(','))
  }
  const blob = new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `audit-events-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.main-tabs { margin-bottom: 16px; }
.sub-tabs { margin-bottom: 12px; }
.filter-row { margin-bottom: 12px; }
.filter-row .input { width: 220px; }
.check { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #4a5160; }
.actions { display: flex; flex-wrap: wrap; gap: 4px; }
.more-row { text-align: center; padding: 12px; }

.modal-mask {
  position: fixed; inset: 0; background: rgba(20, 24, 34, 0.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 75; padding: 24px;
}
.modal-card {
  width: min(820px, 100%); max-height: 84vh;
  background: #fff; border-radius: 14px; box-shadow: 0 16px 48px rgba(20, 24, 34, 0.22);
  display: flex; flex-direction: column; overflow: hidden;
}
.modal-card.small { width: min(460px, 100%); }
.modal-head {
  flex: none; display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid #eef0f4;
}
.modal-title { font-size: 14px; font-weight: 600; }
.detail-body { overflow-y: auto; padding: 12px 16px; }
.detail-row { display: flex; gap: 12px; padding: 6px 0; border-bottom: 1px solid #f4f5f8; }
.detail-key { flex: none; width: 150px; font-size: 12px; color: #818999; }
.detail-value { margin: 0; font-size: 12px; white-space: pre-wrap; word-break: break-all; font-family: ui-monospace, Menlo, monospace; }
.reset-body { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
</style>
