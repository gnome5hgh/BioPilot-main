<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">引用库</h2>
        <p class="page-sub">论文的正式书目记录；新增条目请从论文详情或文献搜索加入。</p>
      </div>
      <div class="toolbar">
        <input v-model="query" class="input" placeholder="搜索标题 / 作者 / 年份" @keyup.enter="load" />
        <button class="btn" @click="load">搜索</button>
        <button class="btn" @click="exportBib">导出 .bib</button>
      </div>
    </div>
    <div v-if="loading" class="empty">正在读取引用库…</div>
    <div v-else-if="!items.length" class="empty">
      引用库还是空的。<br />在文件管理里打开一篇论文，或从文献搜索加入引用，就会出现在这里。
    </div>
    <table v-else class="table">
      <thead>
        <tr><th>Key</th><th>标题</th><th>作者</th><th>年份</th><th>期刊</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="item in items" :key="item.key">
          <td class="mono">{{ item.key }}</td>
          <td>{{ item.title || '—' }}</td>
          <td class="authors" :title="item.authors">{{ item.authors || '—' }}</td>
          <td>{{ item.year || '—' }}</td>
          <td>{{ item.journal || '—' }}</td>
          <td>
            <button class="btn btn-sm" @click="copy(item)">复制引用</button>
            <button class="btn btn-sm btn-danger" @click="remove(item)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="formatPreview" class="preview-card">
      <div class="preview-head">
        <span>引用格式</span>
        <select v-model="format" class="select" @change="copy(currentItem)">
          <option value="author-year">作者-年</option>
          <option value="numbered">数字</option>
          <option value="gbt7714">GB/T 7714</option>
          <option value="bibtex">BibTeX</option>
        </select>
      </div>
      <pre>{{ formatPreview }}</pre>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import http from '../api/auth'
import { confirmDialog } from '../utils/confirm'
import { errText } from '../utils/errors'
import { toast } from '../utils/toast'

const items = ref([])
const query = ref('')
const loading = ref(false)
const format = ref('author-year')
const formatPreview = ref('')
const currentItem = ref(null)

onMounted(load)

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/agent/citations', { params: { q: query.value } })
    items.value = data.entries || []
  } catch (error) {
    toast(errText(error, '引用库读取失败'), 'error')
  } finally {
    loading.value = false
  }
}

async function copy(item) {
  currentItem.value = item
  try {
    const { data } = await http.post('/agent/citations/format', {
      keys: [item.key],
      style: format.value,
    })
    formatPreview.value = data.text || ''
    await navigator.clipboard.writeText(formatPreview.value)
    toast('引用已复制', 'success')
  } catch (error) {
    toast(errText(error, '生成引用失败'), 'error')
  }
}

async function remove(item) {
  const ok = await confirmDialog({
    title: '删除引用条目',
    message: `从引用库删除「${item.title || item.key}」？`,
    detail: '只删除书目记录，不删除论文文件。',
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await http.delete(`/agent/citations/${encodeURIComponent(item.key)}`)
    toast('引用条目已删除', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '删除失败'), 'error')
  }
}

async function exportBib() {
  try {
    const { data } = await http.get('/agent/citations/export')
    const blob = new Blob([data.text || ''], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'references.bib'
    link.click()
    URL.revokeObjectURL(url)
    toast('已导出 references.bib', 'success')
  } catch (error) {
    toast(errText(error, '导出失败'), 'error')
  }
}
</script>

<style scoped>
.authors {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview-card {
  margin-top: 18px;
  border: 1px solid #e6e9ed;
  border-radius: 10px;
  padding: 12px 14px;
  background: #fcfcfd;
}
.preview-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.preview-head .select { height: 30px; font-size: 12px; }
.preview-card pre { margin: 0; white-space: pre-wrap; font-family: ui-monospace, Menlo, monospace; font-size: 12px; color: #4a5160; }
</style>
