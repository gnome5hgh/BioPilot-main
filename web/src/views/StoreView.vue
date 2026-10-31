<template>
  <div class="store">
    <h2>专家 · 技能 · APP</h2>
    <div class="tabs">
      <button v-for="t in tabs" :key="t" :class="{ active: cur === t }" @click="cur = t">{{ t }}</button>
    </div>
    <div v-if="cur === '专家'" class="cards">
      <div v-for="e in experts" :key="e.name" class="card">
        <div class="card-name">{{ e.name }}</div>
        <div class="card-desc">{{ e.description }}</div>
        <div class="card-meta">工具 {{ e.tools_count }} 件</div>
      </div>
    </div>
    <div v-if="cur === '技能'" class="cards">
      <div v-for="s in skills" :key="s.name" class="card">
        <div class="card-name">{{ s.name }} <span class="ver">{{ s.version }}</span>
          <span class="state" :class="{ on: s.enabled }">{{ s.enabled ? '已启用' : '已禁用' }}</span></div>
        <div class="card-desc">{{ s.description }}</div>
      </div>
    </div>
    <div v-if="cur === 'APP'" class="cards">
      <div class="empty">APP 为静态展示（平台预置分析流程，见原型）。</div>
    </div>
    <div class="empty" v-if="cardsEmpty">无数据</div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import http from '../api/auth'

const tabs = ['专家', '技能', 'APP']
const cur = ref('专家')
const experts = ref([])
const skills = ref([])
const cardsEmpty = computed(() =>
  cur.value === '专家' ? experts.value.length === 0 : cur.value === '技能' ? skills.value.length === 0 : false)

onMounted(async () => {
  try {
    const e = await http.get('/agent/store/experts')
    experts.value = e.data.experts
    const s = await http.get('/agent/store/skills')
    skills.value = s.data.skills
  } catch { /* 请求失败时留空态 */ }
})
</script>

<style scoped>
.store { padding: 24px; }
.tabs { display: flex; gap: 12px; margin: 16px 0; }
.tabs button { border: none; background: #f8f9fc; border-radius: 8px; padding: 8px 16px; cursor: pointer; }
.tabs button.active { background: #2ec5b1; color: #fff; }
.cards { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.card { border: 1px solid #e6e9ed; border-radius: 12px; padding: 16px; }
.card-name { font-weight: 600; margin-bottom: 8px; }
.ver { font-size: 12px; color: #a6adbd; margin-left: 6px; }
.state { font-size: 11px; border-radius: 4px; padding: 1px 6px; margin-left: 6px; background: #f0f1f5; color: #818999; }
.state.on { background: #e8f8f5; color: #2ec5b1; }
.card-desc { font-size: 13px; color: #818999; line-height: 1.5; }
.card-meta { font-size: 12px; color: #a6adbd; margin-top: 8px; }
.empty { color: #a6adbd; font-size: 13px; padding: 40px 0; text-align: center; grid-column: 1/-1; }
</style>
