<template>
  <div class="admin">
    <h2>管理端</h2>
    <div class="tabs">
      <button v-for="t in tabs" :key="t" :class="{ active: cur === t }" @click="cur = t">{{ t }}</button>
    </div>

    <div v-if="cur === '用户管理'" class="cards">
      <table>
        <thead><tr><th>用户名</th><th>昵称</th><th>角色</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="u in users" :key="u.userId">
            <td>{{ u.userName }}</td><td>{{ u.nickName }}</td><td>{{ u.role }}</td><td>{{ u.status === '0' ? '正常' : '停用' }}</td>
            <td>
              <button @click="toggleStatus(u)">{{ u.status === '0' ? '停用' : '启用' }}</button>
              <button @click="resetPwd(u)">重置密码</button>
              <button @click="makeAdmin(u)">{{ u.role === 'ADMIN' ? '降为 USER' : '升为 ADMIN' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="cur === '会话总览'" class="cards">
      <table>
        <thead><tr><th>会话</th><th>归属用户</th><th>消息数</th><th>创建时间</th></tr></thead>
        <tbody><tr v-for="s in sessions" :key="s.agent_id">
          <td>{{ s.name || s.agent_id }}</td><td>{{ s.user_id }}</td><td>{{ s.message_count }}</td><td>{{ s.created_at }}</td>
        </tr></tbody>
      </table>
    </div>

    <div v-if="cur === '审计日志'" class="cards">
      <div class="sub-tabs">
        <button :class="{ active: auditSrc === 'events' }" @click="auditSrc = 'events'; loadAudit()">操作审计</button>
        <button :class="{ active: auditSrc === 'logins' }" @click="auditSrc = 'logins'; loadAudit()">登录日志</button>
      </div>
      <table v-if="auditSrc === 'events'">
        <thead><tr><th>时间</th><th>用户</th><th>事件</th><th>工具/角色</th><th>风险</th><th>决策</th><th>结果</th></tr></thead>
        <tbody><tr v-for="e in auditEvents" :key="e.id">
          <td>{{ (e.started_at || '').replace('T', ' ').slice(0, 19) }}</td>
          <td>{{ e.user_id }}</td>
          <td>{{ e.event_type }}</td>
          <td>{{ e.tool_name || e.agent_type || '' }}</td>
          <td>{{ e.risk_level || '' }}</td>
          <td>{{ e.policy_decision || e.approval_outcome || '' }}</td>
          <td>{{ e.result_status || '' }}</td>
        </tr></tbody>
      </table>
      <table v-if="auditSrc === 'logins'">
        <thead><tr><th>用户名</th><th>结果</th><th>IP</th><th>时间</th></tr></thead>
        <tbody><tr v-for="l in audit" :key="l.id">
          <td>{{ l.userName }}</td><td>{{ l.outcome }}</td><td>{{ l.ip }}</td><td>{{ l.createTime }}</td>
        </tr></tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import http from '../api/auth'

const tabs = ['用户管理', '会话总览', '审计日志']
const cur = ref('用户管理')
const users = ref([])
const sessions = ref([])
const audit = ref([])
const auditEvents = ref([])
const auditSrc = ref('events')

async function loadAudit() {
  if (auditSrc.value === 'events') {
    auditEvents.value = (await http.get('/admin/api/audit-events')).data.data || []
  } else {
    audit.value = (await http.get('/admin/api/audit')).data.data || []
  }
}

async function load() {
  users.value = (await http.get('/admin/api/users')).data.data
  sessions.value = (await http.get('/admin/api/sessions')).data.data
  audit.value = (await http.get('/admin/api/audit')).data.data
  loadAudit()
}

async function toggleStatus(u) {
  await http.post(`/admin/api/users/${u.userId}`, { status: u.status === '0' ? '1' : '0' })
  await load()
}

async function makeAdmin(u) {
  await http.post(`/admin/api/users/${u.userId}`, { role: u.role === 'ADMIN' ? 'USER' : 'ADMIN' })
  await load()
}

// 重置密码：管理员现场输入新口令——硬编码公开常量等于给所有账号留后门
async function resetPwd(u) {
  const pwd = window.prompt(`为 ${u.userName} 设置新密码（至少 8 位）：`)
  if (!pwd || pwd.length < 8) return
  await http.post(`/admin/api/users/${u.userId}/reset-password`, { password: pwd })
  window.alert('密码已重置')
}

onMounted(load)
</script>

<style scoped>
.admin { padding: 24px; }
.tabs { display: flex; gap: 12px; margin: 16px 0; }
.tabs button { border: none; background: #f8f9fc; border-radius: 8px; padding: 8px 16px; cursor: pointer; }
.tabs button.active { background: #2ec5b1; color: #fff; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid #e6e9ed; padding: 8px; text-align: left; }
button { border: 1px solid #e6e9ed; background: #fff; border-radius: 6px; padding: 4px 10px; margin-right: 6px; cursor: pointer; font-size: 12px; }
</style>
