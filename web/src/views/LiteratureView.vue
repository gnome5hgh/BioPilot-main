<template>
  <div class="lit">
    <h2>文献搜索</h2>
    <div class="search-row">
      <input v-model="q" placeholder="搜索 PubMed 文献…" @keyup.enter="search" />
      <button @click="search">搜索</button>
    </div>
    <div v-for="r in results" :key="r.id" class="item">
      <div class="t">{{ r.title }}</div>
      <div class="m">{{ r.journal }} · {{ r.pubdate }}</div>
    </div>
    <div class="empty" v-if="!results.length">输入关键词搜索 PubMed。</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import http from '../api/auth'

const q = ref('')
const results = ref([])

async function search() {
  if (!q.value.trim()) return
  const r = await http.get('/agent/literature/search', { params: { q: q.value } })
  results.value = r.data.results
}
</script>

<style scoped>
.lit { padding: 24px; }
.search-row { display: flex; gap: 8px; margin: 16px 0; }
.search-row input { flex: 1; border: 1px solid #e6e9ed; border-radius: 8px; height: 38px; padding: 0 12px; }
.search-row button { background: #2ec5b1; color: #fff; border: none; border-radius: 8px; padding: 0 16px; cursor: pointer; }
.item { border-bottom: 1px solid #e6e9ed; padding: 10px 0; }
.t { font-size: 14px; }
.m { font-size: 12px; color: #a6adbd; }
.empty { color: #a6adbd; font-size: 13px; padding: 40px 0; text-align: center; }
h2 { margin: 0 0 8px; }
</style>
