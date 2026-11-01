<template>
  <div class="store">
    <h2>技能</h2>
    <div class="cards">
      <div v-for="s in skills" :key="s.name" class="card">
        <div class="card-name">{{ s.name }} <span class="ver">{{ s.version }}</span>
          <span class="state" :class="{ on: s.enabled }">{{ s.enabled ? '已启用' : '已禁用' }}</span>
          <button v-if="auth.role === 'ADMIN'" class="toggle" @click="toggle(s)">
            {{ s.enabled ? '禁用' : '启用' }}
          </button>
        </div>
        <div class="card-desc">{{ s.description }}</div>
      </div>
    </div>
    <div class="empty" v-if="skills.length === 0">无数据</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import http from '../api/auth'
import { useAuthStore } from '../api/auth'

const auth = useAuthStore()
const skills = ref([])

onMounted(load)

async function load() {
  try {
    const s = await http.get('/agent/store/skills')
    skills.value = s.data.skills
  } catch { /* 请求失败时留空态 */ }
}

// 启停是管理动作（Java 侧 ADMIN 守卫）：切换后重拉清单
async function toggle(s) {
  try {
    await http.post(`/agent/store/skills/${s.name}/toggle`, { enabled: !s.enabled })
    await load()
  } catch (e) {
    window.alert(e?.response?.data?.msg || '操作失败')
  }
}
</script>

<style scoped>
.store { padding: 24px; }
.cards { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.card { border: 1px solid #e6e9ed; border-radius: 12px; padding: 16px; }
.card-name { font-weight: 600; margin-bottom: 8px; display: flex; align-items: center; }
.ver { font-size: 12px; color: #a6adbd; margin-left: 6px; }
.state { font-size: 11px; border-radius: 4px; padding: 1px 6px; margin-left: 6px; background: #f0f1f5; color: #818999; }
.state.on { background: #e8f8f5; color: #2ec5b1; }
.toggle { margin-left: auto; border: 1px solid #e6e9ed; background: #fff; border-radius: 6px; padding: 2px 10px; cursor: pointer; font-size: 12px; }
.card-desc { font-size: 13px; color: #818999; line-height: 1.5; }
.empty { color: #a6adbd; font-size: 13px; padding: 40px 0; text-align: center; }
</style>
