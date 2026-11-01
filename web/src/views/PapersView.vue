<template>
  <div class="papers">
    <h2>论文目录</h2>
    <div class="upload-row">
      <input ref="fileInput" type="file" accept=".pdf,application/pdf" @change="onPick" />
      <button :disabled="uploading" @click="uploadFile">{{ uploading ? '上传中…' : '上传 PDF' }}</button>
      <span v-if="uploadMsg" class="msg" :class="{ err: uploadErr }">{{ uploadMsg }}</span>
    </div>
    <details class="manual">
      <summary>登记已有 OSS 对象（高级）</summary>
      <div class="upload-row">
        <input v-model="title" placeholder="论文标题" />
        <input v-model="ossKey" placeholder="OSS 对象键（users/&lt;uid&gt;/papers/…）" />
        <button @click="register">登记</button>
      </div>
    </details>
    <table>
      <thead><tr><th>标题</th><th>索引状态</th><th>大小</th><th>时间</th><th>操作</th></tr></thead>
      <tbody><tr v-for="p in papers" :key="p.id">
        <td>{{ p.title || '（未命名）' }}</td>
        <td>{{ p.indexed ? '已索引' : '未索引' }}</td>
        <td>{{ (p.size_bytes / 1024).toFixed(0) }} KB</td>
        <td>{{ p.created_at }}</td>
        <td><button @click="del(p)">删除</button></td>
      </tr></tbody>
    </table>
    <div class="kb">
      <h3>RAG 知识库状态</h3>
      <div>{{ kbSummary }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import http from '../api/auth'

const papers = ref([])
const fileInput = ref(null)
const uploading = ref(false)
const uploadMsg = ref('')
const uploadErr = ref(false)
const title = ref('')
const ossKey = ref('')
const kbSummary = computed(() => {
  const done = papers.value.filter(p => p.indexed).length
  return `已索引 ${done} / ${papers.value.length} 篇`
})

onMounted(load)

async function load() {
  papers.value = (await http.get('/agent/papers')).data.papers
}

// 文件直传：multipart 经 SpringBoot 转发到适配层，对象先落 MinIO、行后落库
async function uploadFile() {
  const f = fileInput.value?.files?.[0]
  if (!f) {
    uploadErr.value = true
    uploadMsg.value = '请先选择 PDF 文件'
    return
  }
  uploading.value = true
  uploadErr.value = false
  uploadMsg.value = ''
  try {
    const form = new FormData()
    form.append('file', f)
    await http.post('/agent/papers/upload', form)
    uploadMsg.value = `已上传：${f.name}`
    fileInput.value.value = ''
    await load()
  } catch (e) {
    uploadErr.value = true
    uploadMsg.value = e?.response?.data?.msg || e?.response?.data?.detail || '上传失败'
  } finally {
    uploading.value = false
  }
}

// 手工登记：对象已在 OSS 时只补元数据行
async function register() {
  await http.post(`/agent/papers/${crypto.randomUUID()}`,
                  { title: title.value, oss_key: ossKey.value, size_bytes: 0 })
  title.value = ''
  ossKey.value = ''
  await load()
}

async function del(p) {
  await http.delete(`/agent/papers/${p.id}`)
  await load()
}
</script>

<style scoped>
.papers { padding: 24px; }
.upload-row { display: flex; gap: 8px; margin: 16px 0; align-items: center; }
.upload-row input[type="file"] { flex: 1; }
.upload-row input { flex: 1; border: 1px solid #e6e9ed; border-radius: 8px; height: 36px; padding: 0 10px; }
.upload-row button { background: #2ec5b1; color: #fff; border: none; border-radius: 8px; padding: 0 16px; cursor: pointer; }
.upload-row button:disabled { opacity: .6; cursor: default; }
.msg { font-size: 12px; color: #2ec5b1; }
.msg.err { color: #e5484d; }
.manual summary { cursor: pointer; font-size: 13px; color: #818999; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid #e6e9ed; padding: 8px; text-align: left; }
button { border: 1px solid #e6e9ed; background: #fff; border-radius: 6px; padding: 4px 10px; cursor: pointer; }
.kb { margin-top: 24px; font-size: 13px; color: #818999; }
</style>
