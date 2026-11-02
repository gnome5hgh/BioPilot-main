<template>
  <div v-if="target" class="modal-mask" @click.self="close">
    <div class="modal-card">
      <div class="modal-head">
        <span class="modal-title">{{ target.name }}</span>
        <div class="row-gap">
          <a v-if="url" :href="url" target="_blank" rel="noreferrer" class="btn btn-sm">新标签打开</a>
          <button v-if="url" class="btn btn-sm" @click="download">下载</button>
          <button class="btn btn-sm" @click="close">关闭</button>
        </div>
      </div>
      <div v-if="loading" class="empty">正在加载…</div>
      <div v-else-if="error" class="empty">{{ error }}</div>
      <iframe v-else-if="kind === 'pdf'" class="preview-frame" :src="url"></iframe>
      <div v-else-if="kind === 'image'" class="preview-image">
        <img :src="url" :alt="target.name" />
      </div>
      <MarkdownView v-else-if="kind === 'markdown'" class="preview-text" :content="text" />
      <pre v-else-if="kind === 'text'" class="preview-text">{{ text }}</pre>
      <div v-else-if="kind === 'csv'" class="preview-table">
        <table class="table">
          <tbody>
            <tr v-for="(line, index) in rows" :key="index">
              <td v-for="(cell, cellIndex) in line" :key="cellIndex">{{ cell }}</td>
            </tr>
          </tbody>
        </table>
        <div class="faint csv-note">仅显示前 {{ rows.length }} 行</div>
      </div>
      <div v-else class="empty">
        这种格式不支持在线预览。<br />
        <button class="btn btn-sm" @click="download">下载文件</button>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 文件预览弹层：论文/数据文件统一入口，按扩展名分流 PDF / 图片 / Markdown / 表格 / 文本。
 *
 * 只负责「取 blob + 展示」，不开业务口子；target 置空即关闭并释放 object URL。
 */
import { onBeforeUnmount, ref, watch } from 'vue'
import MarkdownView from './MarkdownView.vue'
import { errText } from '../utils/errors'
import { toast } from '../utils/toast'
import { fetchFileBlob, parseCsvPreview, previewKind, triggerDownload } from '../utils/files'

const props = defineProps({
  // { kind: 'paper'|'file', id, name }；null 表示关闭
  target: { type: Object, default: null },
})
const emit = defineEmits(['close'])

const loading = ref(false)
const error = ref('')
const kind = ref('')
const text = ref('')
const rows = ref([])
const url = ref('')

let objectUrl = ''
// 快速切换文件时，晚到的旧响应不能覆盖新文件的内容
let loadToken = 0

watch(() => props.target, (target) => {
  if (!target?.id) {
    cleanup()
    return
  }
  load(target)
}, { immediate: true })

onBeforeUnmount(cleanup)

function cleanup() {
  loadToken += 1
  loading.value = false
  error.value = ''
  kind.value = ''
  text.value = ''
  rows.value = []
  url.value = ''
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl)
    objectUrl = ''
  }
}

async function load(target) {
  cleanup()
  const token = ++loadToken
  loading.value = true
  try {
    const blob = await fetchFileBlob(target.kind, target.id)
    if (token !== loadToken) return
    const view = previewKind(target.name)
    if (view === 'pdf' || view === 'image' || view === 'binary') {
      objectUrl = URL.createObjectURL(blob)
      url.value = objectUrl
    } else if (view === 'csv') {
      const body = await blob.text()
      if (token !== loadToken) return
      rows.value = parseCsvPreview(body, (target.name || '').toLowerCase().endsWith('.tsv') ? '\t' : ',')
    } else {
      text.value = await blob.text()
      if (token !== loadToken) return
    }
    kind.value = view
  } catch (err) {
    if (token === loadToken) error.value = errText(err, '预览加载失败，可直接下载')
  } finally {
    if (token === loadToken) loading.value = false
  }
}

function close() {
  emit('close')
}

async function download() {
  if (!props.target?.id) return
  try {
    const blob = await fetchFileBlob(props.target.kind, props.target.id, { download: true })
    triggerDownload(blob, props.target.name)
  } catch (error_) {
    toast(errText(error_, '下载失败'), 'error')
  }
}
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(20, 24, 34, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
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
.modal-title {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview-frame { flex: 1; border: none; width: 100%; }
.preview-image {
  flex: 1;
  overflow: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8f9fc;
}
.preview-image img { max-width: 100%; max-height: 100%; }
.preview-text {
  flex: 1;
  overflow: auto;
  margin: 0;
  padding: 18px 22px;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.75;
}
.preview-table { flex: 1; overflow: auto; padding: 10px 14px; }
.csv-note { padding: 6px 2px; }
</style>
