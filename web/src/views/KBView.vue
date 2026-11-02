<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">知识库</h2>
        <p class="page-sub">文件管理里的论文不会自动进入知识库；勾选加入后才会被检索命中。</p>
      </div>
      <div class="toolbar">
        <button class="btn" @click="load">刷新</button>
        <button class="btn" :disabled="status.running" @click="rebuildAll">
          {{ status.running ? '正在索引…' : '全部重新索引' }}
        </button>
      </div>
    </div>

    <div class="overview">
      <div class="stat-card">
        <div class="stat-n">{{ status.total_papers }}</div>
        <div class="stat-l">文件管理中的论文</div>
      </div>
      <div class="stat-card">
        <div class="stat-n">{{ status.kb_enabled }}</div>
        <div class="stat-l">已加入知识库</div>
      </div>
      <div class="stat-card">
        <div class="stat-n brand">{{ status.indexed }}</div>
        <div class="stat-l">已就绪</div>
      </div>
      <div class="stat-card">
        <div class="stat-n warn">{{ status.queued + status.indexing }}</div>
        <div class="stat-l">处理中</div>
      </div>
      <div class="stat-card">
        <div class="stat-n danger">{{ status.failed }}</div>
        <div class="stat-l">失败</div>
      </div>
      <div class="stat-card">
        <div class="stat-n">{{ status.chunks }}</div>
        <div class="stat-l">分块总数</div>
      </div>
    </div>

    <div class="meta-row">
      <span>向量集合：<span class="mono">{{ status.collection }}</span></span>
      <span>Embedding：{{ status.embedding_model || '—' }}</span>
      <span>最近索引：{{ status.last_indexed_at ? fmtDateTime(status.last_indexed_at) : '—' }}</span>
      <span v-if="status.last_run">
        上轮结果：成功 {{ status.last_run.indexed }} · 失败 {{ status.last_run.failed }} · 清理 {{ status.last_run.removed }}
      </span>
    </div>

    <div class="tabs">
      <button :class="{ active: tab === 'in' }" @click="tab = 'in'">已加入知识库 ({{ inPapers.length }})</button>
      <button :class="{ active: tab === 'out' }" @click="tab = 'out'">未加入 ({{ outPapers.length }})</button>
      <button :class="{ active: tab === 'test' }" @click="tab = 'test'">试检索</button>
    </div>

    <template v-if="tab === 'in'">
      <div v-if="!inPapers.length" class="empty">
        知识库还是空的。去「未加入」勾选论文，或到文件管理上传 PDF。
      </div>
      <table v-else class="table">
        <thead>
          <tr><th>论文</th><th>状态</th><th>分块</th><th>最近索引</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="paper in inPapers" :key="paper.id">
            <td>
              <div class="name-cell">
                <span class="name-main">{{ paper.file_name || '未命名论文' }}</span>
                <span v-if="paper.title" class="name-sub">{{ paper.title }}</span>
                <span v-if="paper.index_error" class="error-text">{{ paper.index_error }}</span>
              </div>
            </td>
            <td><span class="badge" :class="statusBadge(paper.index_status)">{{ statusLabel(paper.index_status) }}</span></td>
            <td>{{ paper.chunk_count || 0 }}</td>
            <td>{{ paper.indexed_at ? fmtDateTime(paper.indexed_at) : '—' }}</td>
            <td class="actions">
              <button class="btn btn-sm" @click="showChunks(paper)">查看分块</button>
              <button v-if="paper.index_status === 'failed'" class="btn btn-sm" @click="retry(paper)">重试</button>
              <button class="btn btn-sm" @click="removeKb(paper)">移出知识库</button>
            </td>
          </tr>
        </tbody>
      </table>
    </template>

    <template v-else-if="tab === 'out'">
      <div class="toolbar out-toolbar">
        <input v-model="outQuery" class="input" placeholder="搜索未加入的论文" />
        <button class="btn btn-primary" :disabled="!outSelected.size" @click="addSelected">
          加入知识库{{ outSelected.size ? `（${outSelected.size}）` : '' }}
        </button>
        <span class="faint">加入后只索引这些论文，不影响文件本身。</span>
      </div>
      <div v-if="!outPapers.length" class="empty">
        没有未加入的论文。上传新 PDF 后，它会先出现在这里。
      </div>
      <table v-else class="table">
        <thead>
          <tr>
            <th class="check-col"><input type="checkbox" :checked="allOutChecked" @change="toggleAllOut" /></th>
            <th>论文</th><th>大小</th><th>上传时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="paper in visibleOutPapers" :key="paper.id">
            <td class="check-col">
              <input type="checkbox" :checked="outSelected.has(paper.id)" @change="toggleOut(paper.id)" />
            </td>
            <td>
              <div class="name-cell">
                <span class="name-main">{{ paper.file_name || '未命名论文' }}</span>
                <span v-if="paper.title" class="name-sub">{{ paper.title }}</span>
              </div>
            </td>
            <td>{{ fmtBytes(paper.size_bytes) }}</td>
            <td>{{ fmtDateTime(paper.created_at) }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <template v-else>
      <div class="test-panel">
        <div class="test-form">
          <input v-model="testQuery" class="input test-query"
                 placeholder="输入一句话，看看知识库会召回哪些分块"
                 @keyup.enter="runSearch" />
          <select v-model.number="topK" class="select">
            <option :value="5">Top 5</option>
            <option :value="8">Top 8</option>
            <option :value="12">Top 12</option>
          </select>
          <button class="btn btn-primary" :disabled="searching || !testQuery.trim()" @click="runSearch">
            {{ searching ? '检索中…' : '检索' }}
          </button>
        </div>
        <div v-if="searchMeta" class="test-meta">
          命中 {{ searchResults.length }} 条 · 用时 {{ searchMeta.elapsed_ms }}ms · 查询「{{ searchMeta.query }}」
        </div>
        <div v-if="searchError" class="empty">{{ searchError }}</div>
        <div v-else-if="!searchRan" class="empty">
          输入问题后点检索。这里使用与对话完全相同的检索与精排链路。
        </div>
        <div v-else-if="!searchResults.length" class="empty">
          没有命中任何分块。<br />试试换一个说法、降低 TopK 要求，或确认相关论文已加入知识库并完成索引。
        </div>
        <div v-else class="search-results">
          <div v-for="(hit, index) in searchResults" :key="hit.id" class="hit">
            <div class="hit-head">
              <span class="hit-rank">#{{ index + 1 }}</span>
              <span class="badge" :class="hit.chunk_type === 'text' ? 'badge-muted' : 'badge-info'">
                {{ hit.chunk_type === 'text' ? '正文' : hit.chunk_type === 'table' ? '表格' : '图' }}
              </span>
              <span class="hit-source">{{ hit.file_name || hit.paper_title || '未知来源' }}</span>
              <span v-if="hit.heading" class="faint">{{ hit.heading }}</span>
              <span v-if="hit.page?.length" class="faint">第 {{ hit.page.join(', ') }} 页</span>
              <span class="spacer"></span>
              <span class="hit-score" :title="'RRF 融合分'">score {{ hit.score }}</span>
            </div>
            <div class="hit-text">{{ hit.text }}</div>
          </div>
        </div>
      </div>
    </template>

    <div v-if="chunks.open" class="modal-mask" @click.self="chunks.open = false">
      <div class="modal-card">
        <div class="modal-head">
          <span class="modal-title">{{ chunks.paper?.file_name || chunks.paper?.title }} · 分块</span>
          <button class="btn btn-sm" @click="chunks.open = false">关闭</button>
        </div>
        <div v-if="chunks.loading" class="empty">正在读取分块…</div>
        <div v-else-if="!chunks.items.length" class="empty">这篇论文还没有分块。</div>
        <div v-else class="chunk-list">
          <div v-for="chunk in chunks.items" :key="chunk.id" class="chunk-item">
            <div class="chunk-meta">
              <span class="badge badge-muted">#{{ chunk.chunk_index }}</span>
              <span class="badge" :class="chunk.chunk_type === 'text' ? 'badge-muted' : 'badge-info'">
                {{ chunk.chunk_type === 'text' ? '正文' : chunk.chunk_type === 'table' ? '表格' : '图' }}
              </span>
              <span v-if="chunk.heading" class="faint">{{ chunk.heading }}</span>
              <span v-if="chunk.page?.length" class="faint">第 {{ chunk.page.join(', ') }} 页</span>
            </div>
            <div class="chunk-text">{{ chunk.text }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import http from '../api/auth'
import { confirmDialog } from '../utils/confirm'
import { errText } from '../utils/errors'
import { toast } from '../utils/toast'
import { fmtBytes, fmtDateTime } from '../utils/time'

const status = reactive({
  total_papers: 0, kb_enabled: 0, indexed: 0, queued: 0, indexing: 0,
  failed: 0, not_added: 0, chunks: 0, collection: '', embedding_model: '',
  last_indexed_at: null, running: false, last_run: null,
})
const papers = ref([])
const tab = ref('in')
const outQuery = ref('')
const outSelected = reactive(new Set())
const testQuery = ref('')
const topK = ref(8)
const searching = ref(false)
const searchRan = ref(false)
const searchResults = ref([])
const searchMeta = ref(null)
const searchError = ref('')
const chunks = reactive({ open: false, loading: false, items: [], paper: null })
let pollTimer = null

const inPapers = computed(() => papers.value.filter((paper) => paper.kb_enabled))
const outPapers = computed(() => papers.value.filter((paper) => !paper.kb_enabled))
const visibleOutPapers = computed(() => {
  const text = outQuery.value.trim().toLowerCase()
  if (!text) return outPapers.value
  return outPapers.value.filter((paper) =>
    (paper.file_name || '').toLowerCase().includes(text)
    || (paper.title || '').toLowerCase().includes(text))
})
const allOutChecked = computed(() =>
  visibleOutPapers.value.length > 0
  && visibleOutPapers.value.every((paper) => outSelected.has(paper.id)))

onMounted(load)
onBeforeUnmount(() => { if (pollTimer) window.clearTimeout(pollTimer) })

async function load() {
  try {
    const [statusResp, papersResp] = await Promise.all([
      http.get('/agent/kb/status'),
      http.get('/agent/kb/papers', { params: { filter: 'all' } }),
    ])
    Object.assign(status, statusResp.data)
    papers.value = papersResp.data.papers || []
    schedulePoll()
  } catch (error) {
    toast(errText(error, '知识库状态读取失败'), 'error')
  }
}

function schedulePoll() {
  if (pollTimer) window.clearTimeout(pollTimer)
  const pending = status.running || status.queued > 0 || status.indexing > 0
  if (!pending) return
  pollTimer = window.setTimeout(load, 3000)
}

function statusLabel(value) {
  return {
    not_added: '未加入', queued: '排队中', indexing: '索引中',
    indexed: '已就绪', failed: '失败',
  }[value] || value
}

function statusBadge(value) {
  return {
    not_added: 'badge-muted', queued: 'badge-warn', indexing: 'badge-warn',
    indexed: 'badge-brand', failed: 'badge-danger',
  }[value] || 'badge-muted'
}

function toggleOut(id) {
  if (outSelected.has(id)) outSelected.delete(id)
  else outSelected.add(id)
}

function toggleAllOut(event) {
  if (event.target.checked) visibleOutPapers.value.forEach((paper) => outSelected.add(paper.id))
  else outSelected.clear()
}

async function addSelected() {
  const ids = [...outSelected]
  if (!ids.length) return
  try {
    await http.post('/agent/kb/papers/add', { ids })
    toast(`已加入 ${ids.length} 篇，正在后台索引`, 'success')
    outSelected.clear()
    await load()
  } catch (error) {
    toast(errText(error, '加入知识库失败'), 'error')
  }
}

async function removeKb(paper) {
  const ok = await confirmDialog({
    title: '移出知识库',
    message: `把「${paper.file_name || paper.title}」移出知识库？`,
    detail: '文件仍保留在文件管理里；移出后不再被检索命中。',
    confirmText: '移出',
  })
  if (!ok) return
  try {
    await http.post('/agent/kb/papers/remove', { ids: [paper.id] })
    toast('已移出知识库（文件保留）', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '移出失败'), 'error')
  }
}

async function retry(paper) {
  try {
    await http.post('/agent/kb/papers/retry', { ids: [paper.id] })
    toast('已重新排队索引', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '重试失败'), 'error')
  }
}

async function rebuildAll() {
  const ok = await confirmDialog({
    title: '全部重新索引',
    message: '把已加入知识库的论文全部重新解析与嵌入？',
    detail: '耗时与论文数量成正比；期间检索可能变慢。',
    confirmText: '开始重建',
  })
  if (!ok) return
  try {
    await http.post('/agent/kb/reindex?force=true', {})
    toast('已开始重建，进度会自动刷新', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '重建失败'), 'error')
  }
}

async function showChunks(paper) {
  chunks.open = true
  chunks.loading = true
  chunks.items = []
  chunks.paper = paper
  try {
    const { data } = await http.get(`/agent/kb/papers/${paper.id}/chunks`)
    chunks.items = data.chunks || []
    chunks.paper = data.paper || paper
  } catch (error) {
    toast(errText(error, '分块读取失败'), 'error')
  } finally {
    chunks.loading = false
  }
}

async function runSearch() {
  const query = testQuery.value.trim()
  if (!query) return
  searching.value = true
  searchError.value = ''
  searchRan.value = true
  try {
    const { data } = await http.post('/agent/kb/search', { query, top_k: topK.value })
    searchResults.value = data.results || []
    searchMeta.value = { elapsed_ms: data.elapsed_ms, query: data.query }
  } catch (error) {
    searchResults.value = []
    searchMeta.value = null
    searchError.value = errText(error, '检索失败')
  } finally {
    searching.value = false
  }
}
</script>

<style scoped>
.overview {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
.stat-card {
  border: 1px solid #e6e9ed;
  border-radius: 12px;
  padding: 12px 14px;
  background: #fff;
}
.stat-n { font-size: 22px; font-weight: 700; color: #2f3033; }
.stat-n.brand { color: #1f9e8c; }
.stat-n.warn { color: #b45309; }
.stat-n.danger { color: #b42318; }
.stat-l { margin-top: 2px; font-size: 11px; color: #a6adbd; }

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 11px;
  color: #a6adbd;
  margin-bottom: 16px;
}
.meta-row .mono { font-size: 11px; color: #818999; }

.tabs { display: flex; gap: 6px; margin-bottom: 14px; }
.tabs button {
  border: none;
  background: #f4f6f9;
  border-radius: 8px;
  padding: 7px 12px;
  font-size: 12px;
  color: #4a5160;
  cursor: pointer;
}
.tabs button.active { background: #2ec5b1; color: #fff; }

.out-toolbar { margin-bottom: 10px; }
.out-toolbar .input { width: 260px; }
.check-col { width: 34px; }
.name-cell { display: flex; flex-direction: column; gap: 2px; }
.name-main { color: #2f3033; }
.name-sub { font-size: 11px; color: #a6adbd; }
.error-text { font-size: 11px; color: #b42318; max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.actions { display: flex; flex-wrap: wrap; gap: 4px; }

.test-panel { border: 1px solid #e6e9ed; border-radius: 12px; padding: 14px; }
.test-form { display: flex; gap: 8px; }
.test-query { flex: 1; }
.test-meta { margin-top: 8px; font-size: 11px; color: #a6adbd; }
.search-results { margin-top: 12px; display: flex; flex-direction: column; gap: 10px; }
.hit { border: 1px solid #eef0f4; border-radius: 10px; padding: 10px 12px; background: #fcfcfd; }
.hit-head { display: flex; align-items: center; gap: 8px; font-size: 11px; margin-bottom: 6px; }
.hit-rank { font-weight: 700; color: #2ec5b1; }
.hit-source { color: #4a5160; }
.hit-score { color: #a6adbd; font-family: ui-monospace, Menlo, monospace; }
.hit-text { font-size: 12.5px; line-height: 1.7; color: #4a5160; white-space: pre-wrap; }

.modal-mask {
  position: fixed; inset: 0; background: rgba(20, 24, 34, 0.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 75; padding: 24px;
}
.modal-card {
  width: min(900px, 100%); height: min(720px, 90vh);
  background: #fff; border-radius: 14px; box-shadow: 0 16px 48px rgba(20, 24, 34, 0.22);
  display: flex; flex-direction: column; overflow: hidden;
}
.modal-head {
  flex: none; display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 12px 16px; border-bottom: 1px solid #eef0f4;
}
.modal-title { font-size: 14px; font-weight: 600; }
.chunk-list { flex: 1; overflow-y: auto; padding: 12px 16px; }
.chunk-item { border-bottom: 1px solid #eef0f4; padding: 10px 0; }
.chunk-meta { display: flex; align-items: center; gap: 8px; font-size: 11px; margin-bottom: 5px; }
.chunk-text { font-size: 12.5px; line-height: 1.7; color: #4a5160; white-space: pre-wrap; }

@media (max-width: 1200px) {
  .overview { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
</style>
