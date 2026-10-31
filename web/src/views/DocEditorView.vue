<template>
  <div class="doc">
    <div class="toolbar">
      <input v-model="docName" placeholder="文档名.md" class="name" />
      <button @click="save" :disabled="!docId">保存</button>
      <button @click="create">新建</button>
    </div>
    <div class="list">
      <div v-for="d in docs" :key="d.id" :class="{ sel: d.id === docId }" @click="open(d)">
        {{ d.name }} <span class="ts">{{ d.updated_at?.slice(0, 16) }}</span>
      </div>
    </div>
    <textarea v-model="content" placeholder="markdown 正文…"></textarea>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import http from '../api/auth'

const docs = ref([])
const docId = ref('')
const docName = ref('新文档.md')
const content = ref('')

onMounted(load)

async function load() {
  docs.value = (await http.get('/agent/documents')).data.documents
}

async function open(d) {
  const r = await http.get(`/agent/documents/${d.id}`)
  docId.value = r.data.id
  docName.value = r.data.name
  content.value = r.data.content || ''
}

async function create() {
  const r = await http.post('/agent/documents', { name: docName.value || '新文档.md', content: '' })
  docId.value = r.data.id
  await load()
}

async function save() {
  if (!docId.value) { await create() }
  await http.put(`/agent/documents/${docId.value}`, { content: content.value })
}
</script>

<style scoped>
.doc { padding: 24px; display: flex; flex-direction: column; gap: 12px; height: 100%; }
.toolbar { display: flex; gap: 8px; }
.name { border: 1px solid #e6e9ed; border-radius: 6px; padding: 6px 10px; }
.toolbar button { background: #2ec5b1; color: #fff; border: none; border-radius: 6px; padding: 6px 14px; cursor: pointer; }
.list { display: flex; gap: 8px; flex-wrap: wrap; }
.list > div { border: 1px solid #e6e9ed; border-radius: 6px; padding: 6px 10px; cursor: pointer; font-size: 13px; }
.list > div.sel { border-color: #2ec5b1; background: #e8f8f5; }
.ts { font-size: 11px; color: #a6adbd; margin-left: 4px; }
textarea { flex: 1; min-height: 300px; border: 1px solid #e6e9ed; border-radius: 10px; padding: 14px; font-family: monospace; font-size: 14px; }
</style>
