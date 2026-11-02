<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">文献搜索</h2>
        <p class="page-sub">跨库检索学术文献；有开放获取全文的可加入论文库，或直接让 Agent 分析。加入论文库不会自动进知识库。</p>
      </div>
    </div>

    <div class="search-row">
      <input v-model="query" class="input search-input" placeholder="搜索文献标题、关键词或 DOI（多源聚合）…"
             @keyup.enter="search" />
      <button class="btn btn-primary" :disabled="loading || !query.trim()" @click="search">
        {{ loading ? '搜索中…' : '搜索' }}
      </button>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>
    <div v-if="loading" class="empty">正在检索…</div>
    <div v-else-if="!searched" class="empty">
      输入关键词开始检索。结果可以一键加入论文库，或交给 Agent 继续分析。
    </div>
    <div v-else-if="!results.length" class="empty">
      没有找到相关文献。<br />试试更短的关键词或英文术语。
    </div>

    <div v-else class="results">
      <article v-for="item in results" :key="item.id" class="result">
        <div class="result-top">
          <div class="result-title">{{ item.title }}</div>
          <span v-if="item.is_open_access" class="badge badge-brand">开放获取</span>
        </div>
        <div class="result-meta">
          <span v-if="item.authors">{{ shortAuthors(item.authors) }}</span>
          <span v-if="item.journal">{{ item.journal }}</span>
          <span v-if="item.pubdate">{{ item.pubdate }}</span>
          <span v-if="item.pmid" class="mono">PMID {{ item.pmid }}</span>
          <span v-if="item.doi" class="mono">DOI {{ item.doi }}</span>
        </div>
        <div v-if="item.abstract" class="result-abstract">{{ item.abstract }}</div>
        <div class="result-actions">
          <button v-if="!imported[item.id]" class="btn btn-sm btn-primary"
                  :disabled="importing === item.id" @click="importPaper(item)">
            {{ importing === item.id ? '正在下载…' : '加入论文文件' }}
          </button>
          <span v-else class="badge badge-brand">已在文件管理（未加入知识库）</span>
          <button class="btn btn-sm" @click="analyze(item)">让 Agent 分析</button>
          <button class="btn btn-sm" @click="copyCitation(item)">复制引用</button>
          <a v-if="item.doi" class="btn btn-sm"
             :href="`https://doi.org/${item.doi}`" target="_blank" rel="noreferrer">原文</a>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import http from '../api/auth'
import { useChatStore } from '../stores/chat'
import { errText } from '../utils/errors'
import { toast } from '../utils/toast'

const router = useRouter()
const chatStore = useChatStore()
const query = ref('')
const results = ref([])
const loading = ref(false)
const searched = ref(false)
const error = ref('')
const importing = ref('')
const imported = reactive({})

async function search() {
  const text = query.value.trim()
  if (!text) return
  loading.value = true
  error.value = ''
  searched.value = true
  try {
    const { data } = await http.get('/agent/literature/search', { params: { q: text } })
    results.value = data.results || []
    if (data.error) error.value = '检索服务暂时不可用，请稍后重试。'
  } catch (err) {
    results.value = []
    error.value = errText(err, '检索失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

function shortAuthors(authors) {
  const list = authors.split(',').map((name) => name.trim()).filter(Boolean)
  if (list.length <= 3) return list.join(', ')
  return `${list.slice(0, 3).join(', ')} 等`
}

async function importPaper(item) {
  importing.value = item.id
  try {
    const { data } = await http.post('/agent/literature/import', item)
    imported[item.id] = data.paper_id
    toast('已加入文件管理（未加入知识库），可在文件管理中预览或加入知识库', 'success', 4200)
  } catch (err) {
    toast(errText(err, '加入论文文件失败'), 'error', 4200)
  } finally {
    importing.value = ''
  }
}

async function analyze(item) {
  chatStore.newDraft()
  chatStore.pendingPrompt = `请分析这篇论文：${item.title}`
    + (item.pmid ? `（PMID ${item.pmid}）` : '')
    + (item.doi ? `（DOI ${item.doi}）` : '')
    + '。请先确认能否获取全文，再给出核心贡献、方法、结果与局限。'
  await router.push('/')
}

async function copyCitation(item) {
  const authors = item.authors || ''
  const year = item.pubdate || ''
  const text = [authors, `“${item.title}”`, item.journal, year]
    .filter(Boolean).join('. ')
  try {
    await navigator.clipboard.writeText(text)
    toast('引用已复制', 'success')
  } catch {
    toast('复制失败，请手动选择文本', 'error')
  }
}
</script>

<style scoped>
.search-row { display: flex; gap: 8px; margin-bottom: 18px; }
.search-input { flex: 1; height: 38px; }
.results { display: flex; flex-direction: column; gap: 12px; }
.result {
  border: 1px solid #e6e9ed;
  border-radius: 12px;
  padding: 14px 16px;
  background: #fff;
}
.result-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.result-title { font-size: 14px; font-weight: 600; line-height: 1.5; color: #2f3033; }
.result-meta {
  display: flex; flex-wrap: wrap; gap: 10px;
  margin-top: 6px; font-size: 11px; color: #a6adbd;
}
.result-meta .mono { font-family: ui-monospace, Menlo, monospace; }
.result-abstract {
  margin-top: 8px;
  font-size: 12.5px;
  line-height: 1.7;
  color: #4a5160;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.result-actions { display: flex; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.error-banner {
  background: #fef2f2; color: #b42318; border: 1px solid #fecaca;
  border-radius: 10px; padding: 10px 12px; font-size: 13px; margin-bottom: 12px;
}
</style>
