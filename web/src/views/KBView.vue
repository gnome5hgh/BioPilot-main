<template>
  <div class="kb">
    <h2>RAG 知识库状态</h2>
    <div class="stats">
      <div class="stat"><span class="n">{{ st.total_papers }}</span><span class="l">论文</span></div>
      <div class="stat"><span class="n">{{ st.indexed }}</span><span class="l">已索引</span></div>
      <div class="stat"><span class="n">{{ st.collection }}</span><span class="l">collection</span></div>
    </div>
    <button @click="reindex">重建索引</button>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import http from '../api/auth'

const st = ref({ total_papers: 0, indexed: 0, collection: '' })

onMounted(async () => {
  st.value = (await http.get('/agent/kb/status')).data
})

async function reindex() {
  await http.post('/agent/kb/reindex')
  st.value = (await http.get('/agent/kb/status')).data
}
</script>

<style scoped>
.kb { padding: 24px; }
.stats { display: flex; gap: 24px; margin: 20px 0; }
.stat { display: flex; flex-direction: column; align-items: center; }
.n { font-size: 24px; font-weight: 700; color: #2ec5b1; }
.l { font-size: 12px; color: #a6adbd; }
button { background: #2ec5b1; color: #fff; border: none; border-radius: 8px; padding: 8px 20px; cursor: pointer; }
h2 { margin: 0 0 8px; }
</style>
