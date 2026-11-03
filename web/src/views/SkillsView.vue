<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">技能中心</h2>
        <p class="page-sub">
          安装、启停和管理你自己的 agentskills.io 标准技能包；技能只对你生效，安装/启停在下次对话生效。
        </p>
      </div>
      <div class="toolbar">
        <input v-model="query" class="input" placeholder="搜索已安装技能（名称 / 描述）" />
        <button class="btn" :disabled="loading" @click="load">刷新</button>
      </div>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: tab === 'installed' }" @click="tab = 'installed'">
        已安装 <span class="badge-count">{{ filtered.length }}</span>
      </button>
      <button class="tab" :class="{ active: tab === 'install' }" @click="tab = 'install'">安装技能</button>
    </div>

    <!-- 已安装 -->
    <template v-if="tab === 'installed'">
      <div v-if="loading" class="empty">正在读取技能…</div>
      <div v-else-if="!filtered.length" class="empty">
        还没有安装任何技能。<br />切到「安装技能」，填一个 git 仓库或上传 zip 包。
      </div>
      <div v-else class="skill-list">
        <div v-for="item in filtered" :key="item.name" class="skill-row">
          <div class="skill-main">
            <div class="skill-title">
              <span class="skill-name">{{ item.name }}</span>
              <span v-if="item.version" class="skill-version">v{{ item.version }}</span>
              <a v-if="item.source === 'git' && item.sourceUrl" class="skill-source"
                 :href="item.sourceUrl" target="_blank" rel="noreferrer">{{ sourceLabel(item) }}</a>
              <span v-else class="skill-source">本地压缩包</span>
            </div>
            <p class="skill-desc">{{ item.description }}</p>
            <p class="skill-meta">安装于 {{ (item.installedAt || '').slice(0, 19).replace('T', ' ') }}</p>
          </div>
          <div class="skill-actions">
            <label class="switch" :title="item.enabled ? '停用' : '启用'">
              <input type="checkbox" :checked="item.enabled" @change="toggle(item, $event.target.checked)" />
              <span class="slider"></span>
            </label>
            <button class="btn btn-sm" @click="showDetail(item)">详情</button>
            <button v-if="item.source === 'git'" class="btn btn-sm" @click="update(item)">检查更新</button>
            <button class="btn btn-sm btn-danger" @click="remove(item)">删除</button>
          </div>
        </div>
      </div>
    </template>

    <!-- 安装 -->
    <template v-else>
      <div class="install-grid">
        <section class="install-card">
          <h3>从 Git 仓库安装</h3>
          <p class="hint">支持完整 URL、SSH 地址或 <code>owner/repo</code> 简写；仓库根或一级子目录含 SKILL.md 即可。</p>
          <input v-model="gitSource" class="input" placeholder="例如 mattpocock/skills" />
          <input v-model="gitRef" class="input" placeholder="分支或标签（可选）" />
          <button class="btn" :disabled="inspecting || !gitSource.trim()" @click="inspectGit">
            {{ inspecting ? '拉取中…' : '预览' }}
          </button>
        </section>

        <section class="install-card">
          <h3>上传压缩包</h3>
          <p class="hint">zip 包内含一个或多个技能目录（每个目录带 SKILL.md），单包不超过 50MB。</p>
          <input ref="fileInput" class="input" type="file" accept=".zip" @change="onFile" />
          <button class="btn" :disabled="inspecting || !file" @click="inspectZip">
            {{ inspecting ? '解析中…' : '预览' }}
          </button>
        </section>
      </div>

      <div v-if="preview" class="preview-card">
        <div class="preview-head">
          <strong>将安装 {{ preview.skills.length }} 个技能</strong>
          <button class="btn btn-sm" @click="resetPreview">取消</button>
        </div>
        <div v-for="skill in preview.skills" :key="skill.name" class="preview-skill">
          <div class="skill-title">
            <span class="skill-name">{{ skill.name }}</span>
            <span v-if="skill.version" class="skill-version">v{{ skill.version }}</span>
            <span v-if="skill.license" class="skill-license">{{ skill.license }}</span>
          </div>
          <p class="skill-desc">{{ skill.description }}</p>
          <p class="skill-meta">
            资源：{{ skill.resources.length ? skill.resources.join('、') : '无附加资源' }}
          </p>
        </div>
        <p class="hint">
          仅接受 agentskills.io 标准形态包；包含 tools.py 的包会被拒绝。安装后只对你自己生效。
        </p>
        <button class="btn btn-primary" :disabled="installing" @click="confirmInstall">
          {{ installing ? '安装中…' : '确认安装' }}
        </button>
      </div>

      <p v-if="installError" class="error-text">{{ installError }}</p>
    </template>

    <!-- 详情 -->
    <div v-if="detail" class="detail-mask" @click.self="detail = null">
      <div class="detail-panel">
        <div class="detail-head">
          <div>
            <strong>{{ detail.name }}</strong>
            <span v-if="detail.version" class="skill-version">v{{ detail.version }}</span>
          </div>
          <button class="btn btn-sm" @click="detail = null">关闭</button>
        </div>
        <p class="skill-desc">{{ detail.description }}</p>
        <pre class="detail-content">{{ detail.content }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import http from '../api/auth'
import { confirmDialog } from '../utils/confirm'
import { errText } from '../utils/errors'
import { toast } from '../utils/toast'

const tab = ref('installed')
const query = ref('')
const loading = ref(false)
const skills = ref([])

const gitSource = ref('')
const gitRef = ref('')
const fileInput = ref(null)
const file = ref(null)
const inspecting = ref(false)
const installing = ref(false)
const preview = ref(null)
const installError = ref('')
const detail = ref(null)

const filtered = computed(() => {
  const text = query.value.trim().toLowerCase()
  if (!text) return skills.value
  return skills.value.filter((item) =>
    item.name.toLowerCase().includes(text)
    || (item.description || '').toLowerCase().includes(text))
})

onMounted(load)

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/skill')
    skills.value = data.skills || []
  } catch (error) {
    toast(errText(error, '技能列表读取失败'), 'error')
  } finally {
    loading.value = false
  }
}

function sourceLabel(item) {
  return item.sourceUrl
    ? item.sourceUrl.replace(/^https?:\/\/(www\.)?github\.com\//, '').replace(/\.git$/, '')
    : 'git'
}

async function toggle(item, enabled) {
  try {
    await http.post(`/skill/${encodeURIComponent(item.name)}/toggle`, { enabled })
    item.enabled = enabled
    toast(enabled ? '已启用' : '已停用', 'success')
  } catch (error) {
    toast(errText(error, '启停失败'), 'error')
    await load()
  }
}

async function showDetail(item) {
  try {
    const { data } = await http.get(`/skill/${encodeURIComponent(item.name)}`)
    detail.value = data.skill
  } catch (error) {
    toast(errText(error, '读取详情失败'), 'error')
  }
}

async function update(item) {
  try {
    await http.post(`/skill/${encodeURIComponent(item.name)}/update`)
    toast('已更新到最新版本', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '更新失败'), 'error')
  }
}

async function remove(item) {
  const ok = await confirmDialog({
    title: '删除技能',
    message: `删除技能「${item.name}」？`,
    detail: '会同时移除平台上的技能包；内置能力不受影响。',
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await http.delete(`/skill/${encodeURIComponent(item.name)}`)
    toast('技能已删除', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '删除失败'), 'error')
  }
}

function onFile(event) {
  file.value = event.target.files?.[0] || null
}

async function inspectGit() {
  installError.value = ''
  inspecting.value = true
  try {
    const { data } = await http.post('/skill/inspect', {
      source: gitSource.value.trim(),
      ref: gitRef.value.trim() || null,
    })
    preview.value = data
  } catch (error) {
    installError.value = errText(error, '预览失败')
  } finally {
    inspecting.value = false
  }
}

async function inspectZip() {
  installError.value = ''
  inspecting.value = true
  try {
    const form = new FormData()
    form.append('file', file.value)
    const { data } = await http.post('/skill/inspect/upload', form)
    preview.value = data
  } catch (error) {
    installError.value = errText(error, '预览失败')
  } finally {
    inspecting.value = false
  }
}

async function confirmInstall() {
  if (!preview.value) return
  installError.value = ''
  installing.value = true
  try {
    const { data } = await http.post('/skill/install', { stagingId: preview.value.stagingId })
    toast(`已安装 ${data.skills?.length || 0} 个技能`, 'success')
    resetPreview()
    tab.value = 'installed'
    await load()
  } catch (error) {
    installError.value = errText(error, '安装失败')
  } finally {
    installing.value = false
  }
}

function resetPreview() {
  preview.value = null
  installError.value = ''
  gitSource.value = ''
  gitRef.value = ''
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
}
</script>

<style scoped>
.tabs {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid var(--border, #e5e7eb);
  margin-bottom: 16px;
}

.tab {
  background: none;
  border: none;
  padding: 10px 4px;
  margin-right: 12px;
  cursor: pointer;
  color: var(--muted, #6b7280);
  border-bottom: 2px solid transparent;
  font-size: 14px;
}

.tab.active {
  color: var(--text, #111827);
  border-bottom-color: var(--accent, #2563eb);
  font-weight: 600;
}

.badge-count {
  display: inline-block;
  margin-left: 4px;
  padding: 0 6px;
  border-radius: 10px;
  background: var(--border, #e5e7eb);
  font-size: 12px;
}

.skill-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skill-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  background: #fff;
}

.skill-main {
  min-width: 0;
}

.skill-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.skill-name {
  font-weight: 600;
  font-size: 15px;
}

.skill-version,
.skill-license {
  font-size: 12px;
  color: var(--muted, #6b7280);
  background: #f3f4f6;
  padding: 1px 6px;
  border-radius: 6px;
}

.skill-source {
  font-size: 12px;
  color: var(--accent, #2563eb);
  text-decoration: underline;
}

.skill-desc {
  margin: 6px 0 4px;
  color: #374151;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}

.skill-meta {
  margin: 0;
  color: var(--muted, #6b7280);
  font-size: 12px;
}

.skill-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.switch {
  position: relative;
  display: inline-block;
  width: 38px;
  height: 22px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  inset: 0;
  background: #d1d5db;
  border-radius: 22px;
  cursor: pointer;
  transition: 0.2s;
}

.slider::before {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  left: 3px;
  top: 3px;
  background: #fff;
  border-radius: 50%;
  transition: 0.2s;
}

.switch input:checked + .slider {
  background: var(--accent, #2563eb);
}

.switch input:checked + .slider::before {
  transform: translateX(16px);
}

.install-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.install-card {
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  padding: 16px;
  background: #fff;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.install-card h3 {
  margin: 0;
  font-size: 15px;
}

.hint {
  margin: 0;
  color: var(--muted, #6b7280);
  font-size: 12px;
  line-height: 1.5;
}

.preview-card {
  margin-top: 16px;
  border: 1px solid var(--accent, #2563eb);
  border-radius: 10px;
  padding: 16px;
  background: #f8fafc;
}

.preview-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.preview-skill {
  padding: 10px 0;
  border-top: 1px dashed var(--border, #e5e7eb);
}

.error-text {
  margin-top: 12px;
  color: #b91c1c;
  font-size: 13px;
}

.btn-primary {
  background: var(--accent, #2563eb);
  color: #fff;
  border-color: var(--accent, #2563eb);
  margin-top: 10px;
}

.detail-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  justify-content: flex-end;
  z-index: 50;
}

.detail-panel {
  width: min(720px, 92vw);
  height: 100%;
  background: #fff;
  padding: 20px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.detail-content {
  white-space: pre-wrap;
  word-break: break-word;
  background: #f9fafb;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  padding: 14px;
  font-size: 13px;
  line-height: 1.6;
}
</style>
