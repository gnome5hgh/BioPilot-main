<template>
  <div class="files">
    <h2>文件管理</h2>
    <div class="upload-row">
      <input ref="fileInput" type="file" multiple
             accept=".pdf,.csv,.tsv,.xlsx,.xls,.h5ad,.json,.txt,.md,.fasta,.fastq"
             @change="onPick" />
      <button :disabled="uploading" @click="uploadFiles">{{ uploading ? '上传中…' : '上传' }}</button>
      <span v-if="msg" class="msg" :class="{ err: isErr }">{{ msg }}</span>
    </div>
    <table>
      <thead><tr><th>名称</th><th>类型</th><th>索引状态</th><th>大小</th><th>时间</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="p in papers" :key="p.id">
          <td>{{ p.title || '（未命名论文）' }}</td>
          <td><span class="badge paper">论文</span></td>
          <td>{{ p.indexed ? '已索引' : '未索引' }}</td>
          <td>{{ (p.size_bytes / 1024).toFixed(0) }} KB</td>
          <td>{{ p.created_at?.slice(0, 16).replace('T', ' ') }}</td>
          <td><button @click="delPaper(p)">删除</button></td>
        </tr>
        <tr v-for="f in files" :key="f.id">
          <td>{{ f.name }}</td>
          <td><span class="badge data">数据文件</span></td>
          <td>—</td>
          <td>{{ (f.size_bytes / 1024).toFixed(0) }} KB</td>
          <td>{{ f.created_at?.slice(0, 16).replace('T', ' ') }}</td>
          <td><button @click="delFile(f)">删除</button></td>
        </tr>
      </tbody>
    </table>
    <div class="empty" v-if="!papers.length && !files.length">还没有文件。上传后可在对话中引用（📄 按钮）。</div>
  </div>
</template>

<script setup>
// 文件管理：用户全部数据文件的统一入口。PDF 走论文目录通道（入 papers 表 +
// 自动 RAG 索引），其余走通用文件通道（uploads 表，对话引用后挂沙箱）。
import { ref, onMounted } from 'vue'
import http from '../api/auth'

const papers = ref([])
const files = ref([])
const fileInput = ref(null)
const uploading = ref(false)
const msg = ref('')
const isErr = ref(false)

onMounted(load)

async function load() {
  const [p, f] = await Promise.all([
    http.get('/agent/papers'),
    http.get('/agent/files'),
  ])
  papers.value = p.data.papers || []
  files.value = f.data.files || []
}

async function onPick(evt) {
  const list = Array.from(evt.target.files || [])
  if (!list.length) return
  uploading.value = true
  msg.value = ''
  isErr.value = false
  try {
    for (const f of list) {
      if (f.size > 200 * 1024 * 1024) {
        isErr.value = true; msg.value = `「${f.name}」超过 200MB 上限，已跳过`; continue
      }
      const form = new FormData()
      form.append('file', f)
      const isPdf = f.name.toLowerCase().endsWith('.pdf')
      const url = isPdf ? '/agent/papers/upload' : '/agent/files/upload'
      await http.post(url, form)
      if (isPdf) msg.value = `论文「${f.name}」已上传并开始后台索引`
      else msg.value = `文件「${f.name}」已上传`
    }
    await load()
  } catch (e) {
    isErr.value = true
    msg.value = e?.response?.data?.detail || e?.response?.data?.msg || '上传失败'
  } finally {
    uploading.value = false
    evt.target.value = ''
  }
}

async function delPaper(p) {
  if (!window.confirm(`删除论文「${p.title || p.id.slice(0, 8)}」？`)) return
  await http.delete(`/agent/papers/${p.id}`)
  await load()
}

async function delFile(f) {
  // 通用文件暂无删除端点——显示提示（后续补 /files/{id} DELETE）
  window.alert('通用文件删除即将支持')
}
</script>

<style scoped>
.files { padding: 24px; }
.upload-row { display: flex; gap: 8px; margin: 16px 0; align-items: center; }
.upload-row input[type="file"] { flex: 1; }
.upload-row button { background: #2ec5b1; color: #fff; border: none; border-radius: 8px; padding: 0 16px; cursor: pointer; }
.upload-row button:disabled { opacity: .6; }
.msg { font-size: 12px; color: #2ec5b1; }
.msg.err { color: #e5484d; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid #e6e9ed; padding: 8px; text-align: left; }
button { border: 1px solid #e6e9ed; background: #fff; border-radius: 6px; padding: 4px 10px; cursor: pointer; }
.badge { font-size: 11px; border-radius: 4px; padding: 1px 6px; }
.badge.paper { background: #e8f8f5; color: #2ec5b1; }
.badge.data { background: #f0f1f5; color: #818999; }
.empty { color: #a6adbd; font-size: 13px; padding: 40px 0; text-align: center; }
h2 { margin: 0 0 16px; }
</style>
