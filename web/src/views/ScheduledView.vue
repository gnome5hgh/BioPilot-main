<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">定时任务</h2>
        <p class="page-sub">到点把任务文本投进归属会话执行，回答会出现在该会话的聊天流里。</p>
      </div>
    </div>

    <div class="create card">
      <div class="create-row">
        <input v-model="name" class="input" placeholder="任务名（如：每周文献巡检）" />
        <select v-model="conversationId" class="select">
          <option value="" disabled>选择归属会话</option>
          <option v-for="session in sessions" :key="session.agent_id" :value="session.agent_id">
            {{ session.name || `未命名会话 · ${session.agent_id.slice(0, 8)}` }}
          </option>
        </select>
        <select v-model.number="interval" class="select">
          <option v-for="item in intervals" :key="item.value" :value="item.value">
            {{ item.label }}
          </option>
        </select>
        <button class="btn btn-primary" @click="create">创建</button>
      </div>
      <textarea v-model="task" class="textarea task"
                placeholder="到点执行的任务内容（如：检索本周单细胞方向的新文献，并生成摘要）"></textarea>
    </div>

    <table class="table">
      <thead>
        <tr>
          <th>名称</th><th>任务</th><th>周期</th><th>归属会话</th>
          <th>下次执行</th><th>上次执行</th><th>状态</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in schedules" :key="item.id">
          <td>{{ item.name }}</td>
          <td class="task-cell" :title="item.task">{{ item.task.slice(0, 48) }}</td>
          <td>{{ cycleLabel(item.interval_minutes) }}</td>
          <td>{{ convName(item.conversation_id) }}</td>
          <td>{{ item.next_run_at ? fmtDateTime(item.next_run_at) : '—' }}</td>
          <td>{{ item.last_run_at ? fmtDateTime(item.last_run_at) : '未执行' }}</td>
          <td>
            <span class="badge" :class="item.paused ? 'badge-muted' : 'badge-brand'">
              {{ item.paused ? '已暂停' : '运行中' }}
            </span>
          </td>
          <td class="actions">
            <button class="btn btn-sm" :disabled="acting === item.id" @click="runNow(item)">立即执行</button>
            <button class="btn btn-sm" :disabled="acting === item.id" @click="toggle(item)">
              {{ item.paused ? '恢复' : '暂停' }}
            </button>
            <button class="btn btn-sm btn-danger" :disabled="acting === item.id" @click="del(item)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="!schedules.length" class="empty">
      还没有定时任务。创建后到点自动执行；结果不会推送通知，回到归属会话查看。
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import http from '../api/auth'
import { confirmDialog } from '../utils/confirm'
import { errText } from '../utils/errors'
import { toast } from '../utils/toast'
import { fmtDateTime } from '../utils/time'

const intervals = [
  { value: 30, label: '每 30 分钟' },
  { value: 60, label: '每 1 小时' },
  { value: 360, label: '每 6 小时' },
  { value: 1440, label: '每天' },
  { value: 10080, label: '每周' },
]

const schedules = ref([])
const sessions = ref([])
const name = ref('')
const task = ref('')
const conversationId = ref('')
const interval = ref(1440)
const acting = ref('')

onMounted(load)

async function load() {
  try {
    const [scheduleResp, sessionResp] = await Promise.all([
      http.get('/schedules'),
      http.get('/conversations', { params: { limit: 100 } }),
    ])
    schedules.value = scheduleResp.data.schedules || []
    sessions.value = sessionResp.data.data || []
    if (!conversationId.value && sessions.value.length) {
      conversationId.value = sessions.value[0].agent_id
    }
  } catch (error) {
    toast(errText(error, '定时任务读取失败'), 'error')
  }
}

function cycleLabel(minutes) {
  return intervals.find((item) => item.value === minutes)?.label || `每 ${minutes} 分钟`
}

function convName(id) {
  const session = sessions.value.find((item) => item.agent_id === id)
  return session
    ? (session.name || `未命名会话 · ${id.slice(0, 8)}`)
    : `未命名会话 · ${id.slice(0, 8)}`
}

async function create() {
  if (!name.value.trim() || !task.value.trim() || !conversationId.value) {
    toast('请填写任务名、任务内容并选择归属会话', 'error')
    return
  }
  try {
    await http.post('/schedules', {
      name: name.value,
      task: task.value,
      conversation_id: conversationId.value,
      interval_minutes: interval.value,
    })
    name.value = ''
    task.value = ''
    toast('定时任务已创建', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '创建失败'), 'error')
  }
}

async function runNow(item) {
  acting.value = item.id
  try {
    await http.post(`/schedules/${item.id}/run`)
    toast('已加入立即执行队列，最多 60 秒后开始', 'success')
  } catch (error) {
    toast(errText(error, '触发失败'), 'error')
  } finally {
    acting.value = ''
  }
}

async function toggle(item) {
  acting.value = item.id
  try {
    await http.patch(`/schedules/${item.id}`, { paused: !item.paused })
    toast(item.paused ? '任务已恢复' : '任务已暂停', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '操作失败'), 'error')
  } finally {
    acting.value = ''
  }
}

async function del(item) {
  const ok = await confirmDialog({
    title: '删除定时任务',
    message: `删除「${item.name}」？`,
    detail: '已产生的回答仍保留在归属会话里。',
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  acting.value = item.id
  try {
    await http.delete(`/schedules/${item.id}`)
    toast('定时任务已删除', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '删除失败'), 'error')
  } finally {
    acting.value = ''
  }
}
</script>

<style scoped>
.create { margin-bottom: 18px; }
.create-row { display: flex; gap: 8px; flex-wrap: wrap; }
.create-row .input { flex: 1; min-width: 220px; }
.task { width: 100%; margin-top: 10px; min-height: 64px; }
.task-cell { color: #818999; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.actions { display: flex; flex-wrap: wrap; gap: 4px; }
</style>
