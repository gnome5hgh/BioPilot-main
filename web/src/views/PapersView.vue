<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">文件管理</h2>
        <p class="page-sub">论文、数据文件与文档统一管理；是否进入知识库由你决定，上传不会自动索引。</p>
      </div>
      <div class="toolbar">
        <input v-model="query" class="input" placeholder="搜索文件名" />
        <select v-model="typeFilter" class="select">
          <option value="all">全部类型</option>
          <option value="paper">论文</option>
          <option value="file">数据文件</option>
          <option value="doc">文档</option>
        </select>
        <select v-model="sortBy" class="select">
          <option value="new">最新优先</option>
          <option value="old">最早优先</option>
          <option value="name">按名称</option>
        </select>
        <button class="btn btn-primary" :disabled="uploading" @click="fileInput?.click()">
          {{ uploading ? '上传中…' : '上传文件' }}
        </button>
        <button class="btn" @click="newDoc">新建文档</button>
      </div>
    </div>

    <input ref="fileInput" type="file" multiple class="file-hidden"
           accept=".pdf,.csv,.tsv,.xlsx,.xls,.h5ad,.json,.txt,.md,.fasta,.fastq"
           @change="onPick" />

    <div class="drop-zone" :class="{ busy: uploading }"
         @dragover.prevent @drop.prevent="onDrop" @click="fileInput?.click()">
      <div class="drop-title">把文件拖到这里，或点击选择</div>
      <div class="drop-sub">PDF 进论文库；CSV / h5ad / xlsx 等进数据文件；.md 进文档</div>
      <label class="drop-check" @click.stop>
        <input type="checkbox" v-model="addToKb" />
        上传 PDF 时同时加入知识库
      </label>
      <div v-if="uploading" class="drop-progress">{{ uploadProgress }}</div>
    </div>

    <div v-if="editing" class="doc-editor">
      <div class="doc-toolbar">
        <input v-model="editing.name" class="input doc-name" placeholder="文档名.md" />
        <div class="seg">
          <button :class="{ active: !docPreview }" @click="docPreview = false">编辑</button>
          <button :class="{ active: docPreview }" @click="docPreview = true">预览</button>
        </div>
        <button class="btn btn-primary" :disabled="saving" @click="saveDoc">
          {{ saving ? '保存中…' : '保存' }}
        </button>
        <button class="btn" @click="closeDoc">关闭</button>
      </div>
      <MarkdownView v-if="docPreview" class="doc-preview" :content="editing.content" />
      <textarea v-else v-model="editing.content" class="textarea doc-text"
                placeholder="markdown 正文…"></textarea>
    </div>

    <div class="list-head">
      <span>共 {{ rows.length }} 项</span>
      <span v-if="selected.size" class="row-gap">
        已选 {{ selected.size }} 项
        <button class="btn btn-sm btn-danger" @click="deleteSelected">删除选中</button>
      </span>
      <span class="spacer"></span>
      <button class="btn btn-sm" @click="load">刷新</button>
    </div>

    <table class="table">
      <thead>
        <tr>
          <th class="check-col"><input type="checkbox" :checked="allChecked" @change="toggleAll" /></th>
          <th>名称</th>
          <th>类型</th>
          <th>知识库</th>
          <th>大小</th>
          <th>更新时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in visibleRows" :key="row.key">
          <td class="check-col">
            <input type="checkbox" :checked="selected.has(row.key)"
                   @change="toggleSelect(row.key)" />
          </td>
          <td>
            <div class="name-cell">
              <span class="name-main">{{ row.name }}</span>
              <span v-if="row.title && row.title !== row.name" class="name-sub">{{ row.title }}</span>
            </div>
          </td>
          <td>
            <span class="badge" :class="typeBadge(row.kind)">{{ typeLabel(row.kind) }}</span>
          </td>
          <td>
            <template v-if="row.kind === 'paper'">
              <span class="badge" :class="statusBadge(row.status)">{{ statusLabel(row.status) }}</span>
              <span v-if="row.status === 'indexed' && row.chunks" class="chunk-count">{{ row.chunks }} 块</span>
              <div v-if="row.status === 'failed' && row.error" class="error-text" :title="row.error">
                {{ row.error }}
              </div>
            </template>
            <span v-else class="faint">—</span>
          </td>
          <td>{{ row.size ? fmtBytes(row.size) : '—' }}</td>
          <td>{{ fmtDateTime(row.time) }}</td>
          <td class="actions">
            <template v-if="row.kind === 'doc'">
              <button class="btn btn-sm" @click="openDoc(row)">编辑</button>
              <button class="btn btn-sm" @click="previewDoc(row)">预览</button>
            </template>
            <template v-else>
              <button class="btn btn-sm" @click="openPreview(row)">预览</button>
              <button class="btn btn-sm" @click="download(row)">下载</button>
            </template>
            <template v-if="row.kind === 'paper'">
              <button v-if="!row.kb" class="btn btn-sm" @click="addKb(row)">加入知识库</button>
              <button v-else class="btn btn-sm" @click="removeKb(row)">移出知识库</button>
              <button v-if="row.status === 'failed'" class="btn btn-sm" @click="retryKb(row)">重试</button>
              <button v-if="row.kb" class="btn btn-sm" @click="showChunks(row)">分块</button>
              <button class="btn btn-sm" :disabled="citing === row.id" @click="addCitation(row)">
                {{ citing === row.id ? '入库中…' : '加入引用库' }}
              </button>
            </template>
            <button class="btn btn-sm btn-danger" @click="removeRow(row)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="!visibleRows.length && !loading" class="empty">
      <template v-if="rows.length">没有匹配的文件，试试清空搜索或切换类型。</template>
      <template v-else>
        还没有文件。<br />把 PDF 拖进来会进入论文库；勾选“同时加入知识库”才会被检索命中。
      </template>
    </div>
    <div v-if="loading" class="empty">正在读取文件清单…</div>

    <!-- 预览弹层 -->
    <FilePreviewModal :target="previewTarget" @close="previewTarget = null" />

    <!-- 分块弹层 -->
    <div v-if="chunks.open" class="modal-mask" @click.self="chunks.open = false">
      <div class="modal-card">
        <div class="modal-head">
          <span class="modal-title">{{ chunks.paper?.file_name || chunks.paper?.title }} · 分块</span>
          <button class="btn btn-sm" @click="chunks.open = false">关闭</button>
        </div>
        <div v-if="chunks.loading" class="empty">正在读取分块…</div>
        <div v-else-if="!chunks.items.length" class="empty">
          这篇论文还没有索引分块。先加入知识库并等索引完成。
        </div>
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
import FilePreviewModal from '../components/FilePreviewModal.vue'
import MarkdownView from '../components/MarkdownView.vue'
import http from '../api/auth'
import { confirmDialog } from '../utils/confirm'
import { errText } from '../utils/errors'
import { fetchFileBlob, triggerDownload } from '../utils/files'
import { toast } from '../utils/toast'
import { fmtBytes, fmtDateTime } from '../utils/time'

const papers = ref([])
const files = ref([])
const docs = ref([])
const loading = ref(false)
const uploading = ref(false)
const uploadProgress = ref('')
const addToKb = ref(false)
const query = ref('')
const typeFilter = ref('all')
const sortBy = ref('new')
const selected = reactive(new Set())
const fileInput = ref(null)

const editing = ref(null)
const editingOrigin = ref({ name: '', content: '' })
const docPreview = ref(false)
const saving = ref(false)
const citing = ref('')

const previewTarget = ref(null)
const chunks = reactive({ open: false, loading: false, items: [], paper: null })
let pollTimer = null

const rows = computed(() => {
  const items = []
  for (const paper of papers.value) {
    items.push({
      key: `paper:${paper.id}`,
      kind: 'paper',
      id: paper.id,
      name: paper.file_name || paper.title || '未命名论文',
      title: paper.title || '',
      size: paper.size_bytes,
      time: paper.created_at,
      kb: Boolean(paper.kb_enabled),
      status: paper.index_status || 'not_added',
      chunks: paper.chunk_count || 0,
      error: paper.index_error || '',
      raw: paper,
    })
  }
  for (const file of files.value) {
    items.push({
      key: `file:${file.id}`,
      kind: 'file',
      id: file.id,
      name: file.name,
      title: '',
      size: file.size_bytes,
      time: file.created_at,
      kb: false,
      status: 'not_added',
      chunks: 0,
      error: '',
      raw: file,
    })
  }
  for (const doc of docs.value) {
    items.push({
      key: `doc:${doc.id}`,
      kind: 'doc',
      id: doc.id,
      name: doc.name,
      title: '',
      size: 0,
      time: doc.updated_at,
      kb: false,
      status: 'not_added',
      chunks: 0,
      error: '',
      raw: doc,
    })
  }
  return items
})

const visibleRows = computed(() => {
  const text = query.value.trim().toLowerCase()
  let items = rows.value
  if (typeFilter.value !== 'all') items = items.filter((row) => row.kind === typeFilter.value)
  if (text) {
    items = items.filter((row) =>
      row.name.toLowerCase().includes(text) || (row.title || '').toLowerCase().includes(text))
  }
  const sorted = [...items]
  if (sortBy.value === 'name') sorted.sort((a, b) => a.name.localeCompare(b.name, 'zh'))
  else {
    sorted.sort((a, b) => new Date(a.time || 0) - new Date(b.time || 0))
    if (sortBy.value === 'new') sorted.reverse()
  }
  return sorted
})

const allChecked = computed(() =>
  visibleRows.value.length > 0 && visibleRows.value.every((row) => selected.has(row.key)))

const docDirty = computed(() => {
  if (!editing.value) return false
  return editing.value.name !== editingOrigin.value.name
    || editing.value.content !== editingOrigin.value.content
})

onMounted(load)
onBeforeUnmount(() => {
  if (pollTimer) window.clearTimeout(pollTimer)
})

async function load() {
  loading.value = true
  try {
    const [paperResp, fileResp, docResp] = await Promise.all([
      http.get('/agent/papers'),
      http.get('/agent/files'),
      http.get('/agent/documents'),
    ])
    papers.value = paperResp.data.papers || []
    files.value = fileResp.data.files || []
    docs.value = docResp.data.documents || []
    schedulePoll()
  } catch (error) {
    toast(errText(error, '文件清单加载失败'), 'error')
  } finally {
    loading.value = false
  }
}

function schedulePoll() {
  if (pollTimer) window.clearTimeout(pollTimer)
  const pending = papers.value.some((paper) =>
    paper.index_status === 'queued' || paper.index_status === 'indexing')
  if (!pending) return
  pollTimer = window.setTimeout(load, 3000)
}

function typeLabel(kind) {
  return { paper: '论文', file: '数据文件', doc: '文档' }[kind] || kind
}

function typeBadge(kind) {
  return { paper: 'badge-brand', file: 'badge-muted', doc: 'badge-info' }[kind]
}

function statusLabel(status) {
  return {
    not_added: '未加入',
    queued: '排队中',
    indexing: '索引中',
    indexed: '已就绪',
    failed: '失败',
  }[status] || status
}

function statusBadge(status) {
  return {
    not_added: 'badge-muted',
    queued: 'badge-warn',
    indexing: 'badge-warn',
    indexed: 'badge-brand',
    failed: 'badge-danger',
  }[status] || 'badge-muted'
}

function toggleSelect(key) {
  if (selected.has(key)) selected.delete(key)
  else selected.add(key)
}

function toggleAll(event) {
  if (event.target.checked) visibleRows.value.forEach((row) => selected.add(row.key))
  else selected.clear()
}

function onPick(event) {
  uploadList(Array.from(event.target.files || []))
  event.target.value = ''
}

function onDrop(event) {
  uploadList(Array.from(event.dataTransfer?.files || []))
}

async function uploadList(list) {
  if (!list.length || uploading.value) return
  uploading.value = true
  let done = 0
  try {
    for (const file of list) {
      done += 1
      uploadProgress.value = `正在上传 ${done}/${list.length}：${file.name}`
      const lower = file.name.toLowerCase()
      const limit = lower.endsWith('.pdf') ? 200 * 1024 * 1024 : 100 * 1024 * 1024
      if (file.size > limit) {
        toast(`「${file.name}」超过 ${Math.round(limit / 1024 / 1024)}MB 上限，已跳过`, 'error')
        continue
      }
      try {
        if (lower.endsWith('.md')) {
          const content = await file.text()
          await http.post('/agent/documents', { name: file.name, content })
          toast(`文档「${file.name}」已创建`, 'success')
        } else if (lower.endsWith('.pdf')) {
          const form = new FormData()
          form.append('file', file)
          form.append('add_to_kb', addToKb.value ? 'true' : 'false')
          await http.post('/agent/papers/upload', form)
          toast(addToKb.value
            ? `论文「${file.name}」已上传，正在后台索引`
            : `论文「${file.name}」已加入文件管理（未加入知识库）`, 'success')
        } else {
          const form = new FormData()
          form.append('file', file)
          await http.post('/agent/files/upload', form)
          toast(`数据文件「${file.name}」已上传`, 'success')
        }
      } catch (error) {
        toast(errText(error, `「${file.name}」上传失败`), 'error')
      }
    }
    await load()
  } finally {
    uploading.value = false
    uploadProgress.value = ''
  }
}

async function addKb(row) {
  try {
    await http.post('/agent/kb/papers/add', { ids: [row.id] })
    toast('已加入知识库，正在后台索引', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '加入知识库失败'), 'error')
  }
}

async function removeKb(row) {
  const ok = await confirmDialog({
    title: '移出知识库',
    message: `把「${row.name}」移出知识库？`,
    detail: '文件仍保留在文件管理里，可随时再加入；移出后不再被检索命中。',
    confirmText: '移出',
  })
  if (!ok) return
  try {
    await http.post('/agent/kb/papers/remove', { ids: [row.id] })
    toast('已移出知识库（文件保留）', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '移出知识库失败'), 'error')
  }
}

async function addCitation(row) {
  citing.value = row.id
  try {
    await http.post('/agent/citations/from-paper', { paper_id: row.id })
    toast('已加入引用库（可在引用库页面复制格式）', 'success')
  } catch (error) {
    toast(errText(error, '加入引用库失败'), 'error')
  } finally {
    citing.value = ''
  }
}

async function retryKb(row) {  try {
    await http.post('/agent/kb/papers/retry', { ids: [row.id] })
    toast('已重新排队索引', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '重试失败'), 'error')
  }
}

async function showChunks(row) {
  chunks.open = true
  chunks.loading = true
  chunks.items = []
  chunks.paper = row.raw
  try {
    const { data } = await http.get(`/agent/kb/papers/${row.id}/chunks`)
    chunks.items = data.chunks || []
    chunks.paper = data.paper || row.raw
  } catch (error) {
    toast(errText(error, '分块读取失败'), 'error')
  } finally {
    chunks.loading = false
  }
}

async function removeRow(row) {
  const ok = await confirmDialog({
    title: '删除文件',
    message: `删除「${row.name}」？`,
    detail: row.kind === 'paper' ? '论文会同时从知识库移除，原文对象一并删除。' : '删除后不可恢复。',
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  await deleteOne(row)
  await load()
}

async function deleteOne(row) {
  const urls = {
    paper: `/agent/papers/${row.id}`,
    file: `/agent/files/${row.id}`,
    doc: `/agent/documents/${row.id}`,
  }
  try {
    await http.delete(urls[row.kind])
    selected.delete(row.key)
  } catch (error) {
    toast(errText(error, '删除失败'), 'error')
  }
}

async function deleteSelected() {
  const targets = rows.value.filter((row) => selected.has(row.key))
  if (!targets.length) return
  const ok = await confirmDialog({
    title: '批量删除',
    message: `删除选中的 ${targets.length} 个文件？`,
    detail: '论文会同时从知识库移除；删除后不可恢复。',
    confirmText: '全部删除',
    danger: true,
  })
  if (!ok) return
  for (const row of targets) await deleteOne(row)
  toast('已删除选中文件', 'success')
  await load()
}

function newDoc() {
  editing.value = { id: '', name: '新文档.md', content: '' }
  editingOrigin.value = { name: '', content: '' }
  docPreview.value = false
}

async function openDoc(row) {
  try {
    const { data } = await http.get(`/agent/documents/${row.id}`)
    editing.value = { id: data.id, name: data.name, content: data.content || '' }
    editingOrigin.value = { name: data.name, content: data.content || '' }
    docPreview.value = false
  } catch (error) {
    toast(errText(error, '文档打开失败'), 'error')
  }
}

async function previewDoc(row) {
  await openDoc(row)
  if (editing.value?.id) docPreview.value = true
}

async function closeDoc() {
  if (docDirty.value) {
    const ok = await confirmDialog({
      title: '放弃未保存的修改？',
      message: '当前文档有未保存的改动。',
      confirmText: '放弃修改',
      danger: true,
    })
    if (!ok) return
  }
  editing.value = null
  docPreview.value = false
}

async function saveDoc() {
  if (!editing.value) return
  saving.value = true
  try {
    if (editing.value.id) {
      await http.put(`/agent/documents/${editing.value.id}`, {
        name: editing.value.name,
        content: editing.value.content,
      })
    } else {
      const { data } = await http.post('/agent/documents', {
        name: editing.value.name || '新文档.md',
        content: editing.value.content,
      })
      editing.value.id = data.id
    }
    editingOrigin.value = { name: editing.value.name, content: editing.value.content }
    toast('文档已保存', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '保存失败'), 'error')
  } finally {
    saving.value = false
  }
}

function openPreview(row) {
  previewTarget.value = { kind: row.kind, id: row.id, name: row.name }
}

async function download(row) {
  try {
    const blob = await fetchFileBlob(row.kind, row.id, { download: true })
    triggerDownload(blob, row.name)
  } catch (error) {
    toast(errText(error, '下载失败'), 'error')
  }
}
</script>

<style scoped>
.file-hidden { display: none; }

.drop-zone {
  border: 1.5px dashed #cfe9e4;
  background: #f9fefd;
  border-radius: 14px;
  padding: 26px 20px;
  text-align: center;
  cursor: pointer;
  margin-bottom: 18px;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.drop-zone:hover { border-color: #2ec5b1; background: #f3fdfa; }
.drop-zone.busy { cursor: default; opacity: 0.8; }
.drop-title { font-size: 14px; font-weight: 600; color: #2f3033; }
.drop-sub { margin-top: 5px; font-size: 12px; color: #a6adbd; }
.drop-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 12px;
  color: #4a5160;
  cursor: pointer;
}
.drop-progress { margin-top: 8px; font-size: 12px; color: #1f9e8c; }

.doc-editor {
  border: 1px solid #e6e9ed;
  border-radius: 12px;
  padding: 14px;
  margin-bottom: 18px;
  background: #fcfcfd;
}
.doc-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.doc-name { flex: 1; }
.doc-text { width: 100%; min-height: 280px; font-family: ui-monospace, Menlo, monospace; font-size: 13px; }
.doc-preview { min-height: 280px; border: 1px solid #eef0f4; border-radius: 10px; padding: 14px; background: #fff; }

.list-head {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #818999;
  margin-bottom: 6px;
}
.check-col { width: 34px; }
.name-cell { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.name-main { color: #2f3033; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 360px; }
.name-sub { font-size: 11px; color: #a6adbd; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 360px; }
.actions { display: flex; flex-wrap: wrap; gap: 4px; }
.chunk-count { margin-left: 6px; font-size: 11px; color: #a6adbd; }
.error-text {
  margin-top: 3px;
  font-size: 11px;
  color: #b42318;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(20, 24, 34, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 75;
  padding: 24px;
}
.modal-card {
  width: min(980px, 100%);
  height: min(760px, 90vh);
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 16px 48px rgba(20, 24, 34, 0.22);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.modal-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid #eef0f4;
}
.modal-title { font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chunk-list { flex: 1; overflow-y: auto; padding: 12px 16px; }
.chunk-item { border-bottom: 1px solid #eef0f4; padding: 10px 0; }
.chunk-meta { display: flex; align-items: center; gap: 8px; font-size: 11px; margin-bottom: 5px; }
.chunk-text { font-size: 12.5px; line-height: 1.7; color: #4a5160; white-space: pre-wrap; }
</style>
