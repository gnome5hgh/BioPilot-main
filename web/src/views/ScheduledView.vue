<template>
  <div class="page">
    <h2>定时任务</h2>
    <div class="create">
      <input v-model="name" placeholder="任务名（如：每周文献巡检）" />
      <select v-model="conversationId">
        <option value="" disabled>选择归属会话</option>
        <option v-for="s in sessions" :key="s.agent_id" :value="s.agent_id">
          {{ s.name || s.agent_id.slice(0, 8) }}
        </option>
      </select>
      <select v-model="interval">
        <option :value="30">每 30 分钟</option>
        <option :value="60">每 1 小时</option>
        <option :value="360">每 6 小时</option>
        <option :value="1440">每天</option>
        <option :value="10080">每周</option>
      </select>
      <button @click="create">创建</button>
    </div>
    <textarea v-model="task" class="task" placeholder="到点执行的任务内容（如：检索本周单细胞方向的新文献，并生成摘要）"></textarea>
    <table>
      <thead><tr><th>名称</th><th>任务</th><th>周期</th><th>归属会话</th><th>上次执行</th><th>状态</th><th>操作</th></tr></thead>
      <tbody><tr v-for="t in schedules" :key="t.id">
        <td>{{ t.name }}</td>
        <td class="task-cell">{{ t.task.slice(0, 40) }}</td>
        <td>每 {{ t.interval_minutes }} 分钟</td>
        <td>{{ convName(t.conversation_id) }}</td>
        <td>{{ t.last_run_at ? t.last_run_at.slice(0, 16).replace('T', ' ') : '未执行' }}</td>
        <td>{{ t.paused ? '已暂停' : '运行中' }}</td>
        <td>
          <button @click="toggle(t)">{{ t.paused ? '恢复' : '暂停' }}</button>
          <button @click="del(t)">删除</button>
        </td>
      </tr></tbody>
    </table>
    <div class="empty" v-if="schedules.length === 0">还没有定时任务。创建后到点会自动把任务投进归属会话执行，回答在对话流里看。</div>
  </div>
</template>

<script setup>
// 定时任务管理：数据与调度执行都在适配层（webapi 进程内 60s 一拍）；
// 到点把任务文本投进归属会话，回答落会话聊天流。
import { ref, onMounted } from 'vue'
import http from '../api/auth'

const schedules = ref([])
const sessions = ref([])
const name = ref('')
const task = ref('')
const conversationId = ref('')
const interval = ref(1440)

onMounted(load)

async function load() {
  const s = await http.get('/agent/schedules')
  schedules.value = s.data.schedules || []
  const sess = await http.get('/sessions', { params: { limit: 100 } })
  sessions.value = sess.data.data || []
  if (!conversationId.value && sessions.value.length) {
    conversationId.value = sessions.value[0].agent_id
  }
}

function convName(cid) {
  const s = sessions.value.find(x => x.agent_id === cid)
  return s ? (s.name || cid.slice(0, 8)) : cid.slice(0, 8)
}

async function create() {
  if (!name.value.trim() || !task.value.trim() || !conversationId.value) {
    window.alert('请填写任务名、任务内容并选择归属会话')
    return
  }
  await http.post('/agent/schedules', {
    name: name.value, task: task.value,
    conversation_id: conversationId.value, interval_minutes: interval.value,
  })
  name.value = ''
  task.value = ''
  await load()
}

async function toggle(t) {
  await http.post(`/agent/schedules/${t.id}/${t.paused ? 'resume' : 'pause'}`)
  await load()
}

async function del(t) {
  await http.delete(`/agent/schedules/${t.id}`)
  await load()
}
</script>

<style scoped>
.page { padding: 24px; }
.create { display: flex; gap: 8px; margin-bottom: 8px; }
.create input, .create select { border: 1px solid #e6e9ed; border-radius: 8px; height: 36px; padding: 0 10px; flex: 1; }
.create button { background: #2ec5b1; color: #fff; border: none; border-radius: 8px; padding: 0 16px; cursor: pointer; }
.task { width: 100%; box-sizing: border-box; min-height: 56px; border: 1px solid #e6e9ed; border-radius: 8px; padding: 8px 10px; font-size: 13px; margin-bottom: 16px; font-family: inherit; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid #e6e9ed; padding: 8px; text-align: left; }
.task-cell { color: #818999; }
button { border: 1px solid #e6e9ed; background: #fff; border-radius: 6px; padding: 4px 10px; cursor: pointer; margin-right: 4px; }
.empty { color: #a6adbd; font-size: 13px; padding: 40px 0; text-align: center; }
h2 { margin: 0 0 16px; }
</style>
