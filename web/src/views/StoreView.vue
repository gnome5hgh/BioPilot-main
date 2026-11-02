<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">技能</h2>
        <p class="page-sub">技能是 Agent 的工作流程包；卡片写明了触发条件与边界。</p>
      </div>
      <div class="toolbar">
        <input v-model="query" class="input" placeholder="搜索技能" />
      </div>
    </div>

    <div v-if="loading" class="empty">正在读取技能…</div>
    <div v-else-if="!visibleSkills.length" class="empty">没有匹配的技能。</div>

    <div v-else class="cards">
      <article v-for="skill in visibleSkills" :key="skill.name" class="card">
        <div class="card-head">
          <span class="card-name">{{ skill.name }}</span>
          <span v-if="skill.version" class="faint">{{ skill.version }}</span>
          <span class="badge" :class="skill.enabled ? 'badge-brand' : 'badge-muted'">
            {{ skill.enabled ? '已启用' : '已禁用' }}
          </span>
          <span class="spacer"></span>
          <button v-if="auth.role === 'ADMIN'" class="btn btn-sm" @click="toggle(skill)">
            {{ skill.enabled ? '禁用' : '启用' }}
          </button>
        </div>
        <div class="card-desc" :class="{ expanded: expanded.has(skill.name) }">{{ skill.description }}</div>
        <div class="card-actions">
          <button v-if="needExpand(skill)" class="btn-link" @click="toggleExpand(skill.name)">
            {{ expanded.has(skill.name) ? '收起' : '展开全文' }}
          </button>
          <span class="spacer"></span>
          <button class="btn btn-sm" @click="useSkill(skill)">用这个技能发起对话</button>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import http, { useAuthStore } from '../api/auth'
import { useChatStore } from '../stores/chat'
import { errText } from '../utils/errors'
import { toast } from '../utils/toast'

const auth = useAuthStore()
const chatStore = useChatStore()
const router = useRouter()
const skills = ref([])
const loading = ref(true)
const query = ref('')
const expanded = reactive(new Set())

const visibleSkills = computed(() => {
  const text = query.value.trim().toLowerCase()
  if (!text) return skills.value
  return skills.value.filter((skill) =>
    skill.name.toLowerCase().includes(text)
    || (skill.description || '').toLowerCase().includes(text))
})

onMounted(load)

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/agent/store/skills')
    skills.value = data.skills || []
  } catch (error) {
    toast(errText(error, '技能清单读取失败'), 'error')
  } finally {
    loading.value = false
  }
}

function needExpand(skill) {
  return (skill.description || '').length > 140
}

function toggleExpand(name) {
  if (expanded.has(name)) expanded.delete(name)
  else expanded.add(name)
}

async function toggle(skill) {
  try {
    await http.post(`/agent/store/skills/${skill.name}/toggle`, { enabled: !skill.enabled })
    toast(skill.enabled ? '技能已禁用' : '技能已启用', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '操作失败'), 'error')
  }
}

async function useSkill(skill) {
  chatStore.newDraft()
  chatStore.pendingPrompt = `请按技能「${skill.name}」的流程完成以下任务：`
  await router.push('/')
}
</script>

<style scoped>
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 14px;
}
.card { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.card-head { display: flex; align-items: center; gap: 8px; }
.card-name { font-weight: 650; font-size: 14px; }
.card-desc {
  font-size: 12.5px;
  color: #818999;
  line-height: 1.75;
  white-space: pre-wrap;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-desc.expanded { display: block; -webkit-line-clamp: unset; }
.card-actions { display: flex; align-items: center; gap: 8px; }
</style>
