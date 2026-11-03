<template>
  <div class="page settings">
    <div class="page-head">
      <div>
        <h2 class="page-title">设置</h2>
        <p class="page-sub">
          运行时配置保存在数据库；保存后下一轮对话生效，标有「需重启」的项要重启引擎。
        </p>
      </div>
      <div class="toolbar">
        <button class="btn" :disabled="loading" @click="load">刷新</button>
      </div>
    </div>

    <div v-if="warning" class="warn-box">{{ warning }}</div>

    <div v-if="loading" class="empty">正在读取配置…</div>

    <template v-else>
      <div class="seg group-tabs">
        <button v-for="group in groups" :key="group.key"
                :class="{ active: activeGroup === group.key }"
                @click="activeGroup = group.key">
          {{ group.label }}
        </button>
      </div>

      <section v-for="group in visibleGroups" :key="group.key" class="card section">
        <div class="group-head">
          <div>
            <div class="group-title">{{ group.label }}</div>
            <div class="group-desc">{{ group.description }}</div>
          </div>
          <span class="badge badge-muted">{{ group.key === 'bootstrap' ? '只读' : '可修改' }}</span>
        </div>

        <div v-for="section in group.sections" :key="section.key" class="sub-section">
          <div class="sub-head">
            <div class="sub-title">{{ section.label }}</div>
            <div v-if="section.description" class="sub-desc">{{ section.description }}</div>
          </div>

          <div v-for="field in section.fields" :key="field.path" class="row field-row">
            <div class="row-main">
              <div class="row-title">
                {{ field.label }}
                <span class="path">{{ field.path }}</span>
                <span class="badge" :class="badgeClass(field.path)">{{ sourceLabel(field.path) }}</span>
                <span v-if="field.requires_restart" class="badge badge-warn">需重启</span>
              </div>
              <div v-if="field.help" class="row-desc">{{ field.help }}</div>
            </div>

            <div class="control">
              <!-- 部署引导：只读展示 -->
              <template v-if="!field.editable">
                <span v-if="field.secret" class="readonly">
                  {{ values[field.path]?.set ? `已配置（末 4 位 ${values[field.path].last4}）` : '未配置' }}
                </span>
                <span v-else class="readonly">{{ display(values[field.path]) }}</span>
              </template>

              <!-- 布尔 -->
              <button v-else-if="field.widget === 'switch'" class="switch"
                      :class="{ on: values[field.path], locked: locked(field) }"
                      :disabled="locked(field)"
                      @click="values[field.path] = !values[field.path]">
                {{ values[field.path] ? '开' : '关' }}
              </button>

              <!-- 枚举 -->
              <select v-else-if="field.widget === 'select'" v-model="values[field.path]"
                      class="select" :disabled="locked(field)">
                <option v-for="option in field.options" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>

              <!-- 数字 -->
              <input v-else-if="field.widget === 'number'" v-model.number="values[field.path]"
                     type="number" class="input number" :disabled="locked(field)" />

              <!-- 密钥 -->
              <div v-else-if="field.widget === 'password'" class="secret-box">
                <input v-model="secretInput[field.path]" type="password" class="input"
                       :disabled="locked(field)"
                       :placeholder="secretPlaceholder(field.path)" />
                <button v-if="values[field.path]?.set && !locked(field)" class="btn btn-sm"
                        @click="clearSecret(field.path)">清除</button>
                <span v-if="secretCleared[field.path]" class="faint">保存后回落环境变量/默认值</span>
              </div>

              <!-- 字符串 -->
              <input v-else-if="field.widget === 'text'" v-model="values[field.path]"
                     class="input wide" :disabled="locked(field)" />

              <!-- 逗号分隔列表 -->
              <input v-else-if="field.widget === 'tags'" v-model="tagsText[field.path]"
                     class="input wide" :disabled="locked(field)"
                     placeholder="逗号分隔，留空表示无" />

              <!-- JSON 结构 -->
              <textarea v-else v-model="jsonText[field.path]" class="input json"
                        :rows="jsonRows(field.path)" spellcheck="false"
                        :disabled="locked(field)"></textarea>
            </div>
          </div>
        </div>
      </section>

      <section class="card section save-card">
        <div class="save-row">
          <input v-model="reason" class="input reason" placeholder="变更说明（可选，写入历史）" />
          <div class="save-actions">
            <span class="faint">当前版本 v{{ version }}</span>
            <button class="btn btn-primary" :disabled="saving" @click="save">
              {{ saving ? '保存中…' : '保存修改' }}
            </button>
          </div>
        </div>
      </section>

      <section class="card section">
        <div class="group-head">
          <div>
            <div class="group-title">保存历史</div>
            <div class="group-desc">每次保存都会留一份完整快照，可按版本回滚。</div>
          </div>
          <button class="btn btn-sm" @click="toggleHistory">
            {{ historyOpen ? '收起' : '查看' }}
          </button>
        </div>
        <div v-if="historyOpen" class="history">
          <div v-if="!historyRows.length" class="empty">还没有保存记录。</div>
          <div v-for="row in historyRows" :key="row.version" class="history-row">
            <div class="history-main">
              <b>v{{ row.version }}</b>
              <span class="faint">{{ row.updated_by || '—' }} · {{ fmtTime(row.created_at) }}</span>
              <div class="history-reason">{{ row.reason || '（无说明）' }}</div>
              <div class="history-paths">{{ (row.changed_paths || []).join('、') || '—' }}</div>
            </div>
            <button class="btn btn-sm" @click="rollback(row.version)">回滚到此版本</button>
          </div>
        </div>
      </section>
    </template>

    <section class="card section">
      <div class="row">
        <div class="row-main">
          <div class="row-title">文献检索源</div>
          <div class="row-desc">
            文献页与 Agent 共用这些检索源。MCP server 连接失败只跳过该源，不影响平台启动。
          </div>
        </div>
        <button class="btn btn-sm" @click="openMcpForm">新增检索源</button>
      </div>

      <div class="mcp-list">
        <div v-for="server in mcpServers" :key="server.id" class="mcp-row">
          <div class="mcp-main">
            <div class="mcp-name">
              {{ server.name }}
              <span class="badge badge-muted">{{ server.transport }}</span>
              <span class="badge" :class="server.enabled ? 'badge-brand' : 'badge-muted'">
                {{ server.enabled ? '启用' : '停用' }}
              </span>
            </div>
            <div class="mcp-desc">{{ server.url || server.command }} · {{ server.adapter }}</div>
          </div>
          <div class="mcp-actions">
            <span class="mcp-status" :class="statusClass(server.name)">{{ statusText(server.name) }}</span>
            <button class="btn btn-sm" @click="testMcp(server)">测试</button>
            <button class="btn btn-sm" @click="toggleMcp(server)">{{ server.enabled ? '停用' : '启用' }}</button>
            <button class="btn btn-sm" @click="editMcp(server)">编辑</button>
            <button class="btn btn-sm danger" @click="removeMcp(server)">删除</button>
          </div>
        </div>
        <div v-if="!mcpServers.length" class="empty">还没有检索源。新增一个 MCP server 后，文献页与 Agent 都能用它检索。</div>
      </div>

      <div v-if="mcpForm.open" class="mcp-form">
        <div class="mcp-form-grid">
          <input v-model="mcpForm.name" class="input" placeholder="名称（字母/数字/_/-）" />
          <select v-model="mcpForm.transport" class="select">
            <option value="http">HTTP（streamable）</option>
            <option value="stdio">stdio</option>
          </select>
          <input v-if="mcpForm.transport === 'http'" v-model="mcpForm.url" class="input wide"
                 placeholder="http://paper-search-mcp:8000/mcp" />
          <input v-else v-model="mcpForm.command" class="input wide" placeholder="uvx" />
          <input v-model="mcpForm.allowedTools" class="input wide"
                 placeholder="允许的工具（逗号分隔；留空=全部）" />
          <label class="mcp-check">
            <input v-model="mcpForm.enabled" type="checkbox" /> 启用
          </label>
        </div>
        <div class="mcp-form-hint">
          只接入返回论文列表的 MCP server（适配器 paper_search）。stdio 的 args/env/headers 走接口配置；密钥不会回显。
        </div>
        <div class="mcp-form-actions">
          <button class="btn btn-sm" @click="mcpForm.open = false">取消</button>
          <button class="btn btn-sm btn-primary" :disabled="mcpSaving" @click="saveMcp">
            {{ mcpSaving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import http from '../api/auth'
import { confirmDialog } from '../utils/confirm'
import { errText } from '../utils/errors'
import { toast } from '../utils/toast'
import { fmtDateTime } from '../utils/time'

const loading = ref(true)
const saving = ref(false)
const version = ref(0)
const groups = ref([])
const values = ref({})
const sources = ref({})
const warning = ref('')
const activeGroup = ref('')
const reason = ref('')

const jsonText = ref({})
const tagsText = ref({})
const secretInput = ref({})
const secretCleared = ref({})
const original = {}

const historyOpen = ref(false)
const historyRows = ref([])

const mcpServers = ref([])
const mcpStatuses = ref({})
const mcpSaving = ref(false)
const mcpForm = reactive({
  open: false, id: '', name: '', transport: 'http', url: '', command: '',
  allowedTools: 'search_papers', enabled: true,
  // 编辑时原样带回：表单不展示这些字段，但漏传会被服务端按默认值覆盖
  disabledTools: [], connectTimeoutMs: null, callTimeoutMs: null,
})

const visibleGroups = computed(() => {
  const selected = groups.value.find((group) => group.key === activeGroup.value)
  return selected ? [selected] : []
})

onMounted(load)

async function load() {
  loading.value = true
  try {
    const { data } = await http.get('/admin/settings')
    applySnapshot(data)
    await Promise.all([loadMcp(), loadMcpStatus()])
    if (historyOpen.value) await loadHistory()
  } catch (error) {
    toast(errText(error, '设置读取失败'), 'error')
  } finally {
    loading.value = false
  }
}

function applySnapshot(data) {
  version.value = data.version || 0
  warning.value = data.warning || ''
  groups.value = data.schema || []
  values.value = data.values || {}
  sources.value = data.sources || {}
  reason.value = ''
  jsonText.value = {}
  tagsText.value = {}
  secretInput.value = {}
  secretCleared.value = {}
  for (const group of groups.value) {
    for (const section of group.sections) {
      for (const field of section.fields) {
        const value = values.value[field.path]
        if (field.widget === 'json') {
          jsonText.value[field.path] = JSON.stringify(value, null, 2)
        } else if (field.widget === 'tags') {
          tagsText.value[field.path] = Array.isArray(value) ? value.join(', ') : ''
        }
        original[field.path] = JSON.stringify(value)
      }
    }
  }
  if (!activeGroup.value) {
    activeGroup.value = groups.value[0]?.key || ''
  }
}

function locked(field) {
  return !field.editable || sources.value[field.path] === 'env'
}

const SOURCE_LABEL = { env: '环境变量', db: '已修改', file: '配置文件', default: '默认' }

function sourceLabel(path) {
  return SOURCE_LABEL[sources.value[path]] || '默认'
}

function badgeClass(path) {
  const source = sources.value[path]
  if (source === 'env') return 'badge-info'
  if (source === 'db') return 'badge-brand'
  return 'badge-muted'
}

function display(value) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function secretPlaceholder(path) {
  const state = values.value[path]
  return state?.set ? `已配置（末 4 位 ${state.last4}），留空保持不变` : '未配置'
}

function clearSecret(path) {
  secretCleared.value[path] = true
  secretInput.value[path] = ''
}

function jsonRows(path) {
  if (path === 'runtime.models') return 8
  if (path === 'agents.timeouts' || path === 'agents.max_turns') return 6
  return 5
}

function collectPatches() {
  const patches = []
  for (const group of groups.value) {
    for (const section of group.sections) {
      for (const field of section.fields) {
        if (!field.editable || sources.value[field.path] === 'env') continue
        // 按控件类型判断，而不是 secret 标记：runtime.models 是密钥载体但控件是
        // JSON 数组编辑器，按 secret 走会把数组当口令字符串提交（422）。
        if (field.widget === 'password') {
          if (secretCleared.value[field.path]) {
            patches.push({ path: field.path, unset: true })
          } else if (secretInput.value[field.path]) {
            patches.push({ path: field.path, value: secretInput.value[field.path] })
          }
          continue
        }
        let value
        if (field.widget === 'json') {
          try {
            value = JSON.parse(jsonText.value[field.path] || 'null')
          } catch {
            throw new Error(`${field.label} 不是合法 JSON`)
          }
        } else if (field.widget === 'tags') {
          value = (tagsText.value[field.path] || '')
            .split(',').map((item) => item.trim()).filter(Boolean)
        } else if (field.widget === 'number') {
          value = Number(values.value[field.path])
        } else {
          value = values.value[field.path]
        }
        if (field.default === null && value === '') value = null
        if (JSON.stringify(value) !== original[field.path]) {
          patches.push({ path: field.path, value })
        }
      }
    }
  }
  return patches
}

async function save() {
  let patches
  try {
    patches = collectPatches()
  } catch (error) {
    toast(error.message, 'error')
    return
  }
  if (!patches.length) {
    toast('没有需要保存的改动', 'info')
    return
  }
  saving.value = true
  try {
    await http.patch('/admin/settings', {
      version: version.value,
      reason: reason.value,
      patches,
    })
    toast('设置已保存，下一轮对话生效', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '保存失败'), 'error')
    if (error?.response?.status === 409) await load()
  } finally {
    saving.value = false
  }
}

async function toggleHistory() {
  historyOpen.value = !historyOpen.value
  if (historyOpen.value) await loadHistory()
}

async function loadHistory() {
  try {
    const { data } = await http.get('/admin/settings/history', { params: { limit: 20 } })
    historyRows.value = data.data || []
  } catch (error) {
    toast(errText(error, '历史读取失败'), 'error')
    historyRows.value = []
  }
}

async function rollback(target) {
  const ok = await confirmDialog({
    title: '回滚配置',
    message: `把配置恢复到版本 v${target}？`,
    detail: '当前版本会保留在历史里，回滚本身也会记一条新历史。',
    confirmText: '回滚',
  })
  if (!ok) return
  try {
    await http.post('/admin/settings/rollback', { version: target })
    toast('已回滚，下一轮对话生效', 'success')
    await load()
  } catch (error) {
    toast(errText(error, '回滚失败'), 'error')
  }
}

function fmtTime(value) {
  return value ? fmtDateTime(value) : '—'
}

// ── 文献检索源（平台表，与运行时配置分开） ──

async function loadMcp() {
  try {
    const { data } = await http.get('/admin/literature/sources')
    mcpServers.value = data.data || []
  } catch (error) {
    toast(errText(error, '检索源读取失败'), 'error')
  }
}

async function loadMcpStatus() {
  try {
    const { data } = await http.get('/admin/literature/sources/status')
    mcpStatuses.value = data.data || {}
  } catch {
    mcpStatuses.value = {}
  }
}

function statusText(name) {
  const status = mcpStatuses.value[name]
  if (!status) return '未连接'
  if (status.state === 'CONNECTED') return `已连接 · ${(status.tools || []).length} 个工具`
  if (status.state === 'FAILED') return '连接失败'
  return '未连接'
}

function statusClass(name) {
  const state = mcpStatuses.value[name]?.state
  return state === 'CONNECTED' ? 'ok' : state === 'FAILED' ? 'bad' : 'idle'
}

function openMcpForm() {
  Object.assign(mcpForm, {
    open: true, id: '', name: '', transport: 'http',
    url: '', command: '',
    allowedTools: 'search_papers', enabled: true,
  })
}

function editMcp(server) {
  Object.assign(mcpForm, {
    open: true,
    id: server.id,
    name: server.name,
    transport: server.transport,
    url: server.url || '',
    command: server.command || '',
    allowedTools: (server.allowedTools || []).join(', '),
    enabled: Boolean(server.enabled),
    disabledTools: server.disabledTools || [],
    connectTimeoutMs: server.connectTimeoutMs ?? null,
    callTimeoutMs: server.callTimeoutMs ?? null,
  })
}

function payload(server, overrides = {}) {
  return {
    name: server.name,
    transport: server.transport,
    url: server.url || '',
    command: server.command || '',
    args: null,
    adapter: server.adapter || 'paper_search',
    allowedTools: server.allowedTools || [],
    disabledTools: server.disabledTools || [],
    enabled: server.enabled,
    ...overrides,
  }
}

async function saveMcp() {
  const name = mcpForm.name.trim()
  if (!name) {
    toast('名称不能为空', 'error')
    return
  }
  const body = {
    name,
    transport: mcpForm.transport,
    url: mcpForm.transport === 'http' ? mcpForm.url.trim() : '',
    command: mcpForm.transport === 'stdio' ? mcpForm.command.trim() : '',
    adapter: 'paper_search',
    allowedTools: mcpForm.allowedTools.split(',').map((item) => item.trim()).filter(Boolean),
    // 编辑时不暴露这两个字段，但必须原样回传：写空数组/默认值等于把用户配置抹掉
    disabledTools: mcpForm.disabledTools || [],
    enabled: mcpForm.enabled,
  }
  // 超时字段在服务端是 int：新建时不传（走默认），编辑时原样带回
  if (mcpForm.connectTimeoutMs != null) body.connectTimeoutMs = mcpForm.connectTimeoutMs
  if (mcpForm.callTimeoutMs != null) body.callTimeoutMs = mcpForm.callTimeoutMs
  mcpSaving.value = true
  try {
    if (mcpForm.id) {
      await http.put(`/admin/literature/sources/${mcpForm.id}`, body)
    } else {
      await http.post('/admin/literature/sources', body)
    }
    mcpForm.open = false
    toast('检索源已保存，正在重连', 'success')
    await Promise.all([loadMcp(), loadMcpStatus()])
  } catch (error) {
    toast(errText(error, '检索源保存失败'), 'error')
  } finally {
    mcpSaving.value = false
  }
}

async function testMcp(server) {
  try {
    const { data } = await http.post(`/admin/literature/sources/${server.id}/test`)
    const status = data.data
    mcpStatuses.value = { ...mcpStatuses.value, [server.name]: status }
    toast(status.state === 'CONNECTED'
      ? `连接成功，发现 ${(status.tools || []).length} 个工具`
      : `连接失败：${status.error || '未知原因'}`, status.state === 'CONNECTED' ? 'success' : 'error')
  } catch (error) {
    toast(errText(error, '测试失败'), 'error')
  }
}

async function toggleMcp(server) {
  try {
    await http.put(`/admin/literature/sources/${server.id}`,
      payload(server, { enabled: !server.enabled }))
    await Promise.all([loadMcp(), loadMcpStatus()])
  } catch (error) {
    toast(errText(error, '切换失败'), 'error')
  }
}

async function removeMcp(server) {
  const ok = await confirmDialog({
    title: '删除检索源',
    message: `删除检索源「${server.name}」？`,
    detail: '删除后，文献检索与 agent 都不再使用该来源。',
    confirmText: '删除',
    danger: true,
  })
  if (!ok) return
  try {
    await http.delete(`/admin/literature/sources/${server.id}`)
    await Promise.all([loadMcp(), loadMcpStatus()])
    toast('已删除', 'success')
  } catch (error) {
    toast(errText(error, '删除失败'), 'error')
  }
}
</script>

<style scoped>
.settings { max-width: 980px; }
.section { margin-bottom: 16px; padding: 0; overflow: hidden; }

.group-tabs { flex-wrap: wrap; margin-bottom: 14px; }
.group-head {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
  padding: 16px 18px; border-bottom: 1px solid #eef0f3;
}
.group-title { font-size: 15px; font-weight: 600; }
.group-desc { margin-top: 4px; font-size: 12px; color: #818999; line-height: 1.7; }

.sub-section { border-bottom: 1px solid #f2f4f7; }
.sub-section:last-child { border-bottom: none; }
.sub-head { padding: 12px 18px 0; }
.sub-title { font-size: 13px; font-weight: 600; color: #4a5160; }
.sub-desc { margin-top: 3px; font-size: 11px; color: #a6adbd; line-height: 1.7; }

.field-row {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 20px; padding: 12px 18px;
}
.field-row + .field-row { border-top: 1px solid #f7f8fa; }
.row-main { min-width: 0; }
.row-title { font-size: 13px; font-weight: 500; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.row-desc { margin-top: 4px; font-size: 11px; color: #818999; line-height: 1.7; }
.path { font-size: 10px; color: #b3b9c6; font-family: ui-monospace, Menlo, monospace; }

.control { flex: none; display: flex; align-items: center; gap: 6px; min-width: 180px; justify-content: flex-end; }
.input, .select { height: 32px; }
.input.wide { width: 320px; }
.input.number { width: 120px; }
.input.json { width: 360px; height: auto; padding: 8px 10px; font-family: ui-monospace, Menlo, monospace; font-size: 11px; line-height: 1.6; }
.input.reason { width: 380px; }
.readonly { font-size: 12px; color: #4a5160; word-break: break-all; max-width: 380px; text-align: right; }
.secret-box { display: flex; align-items: center; gap: 6px; }
.secret-box .input { width: 240px; }

.switch {
  flex: none; border: none; border-radius: 999px; padding: 5px 16px;
  background: #f0f1f5; color: #818999; cursor: pointer; font-size: 12px;
}
.switch.on { background: #2ec5b1; color: #fff; }
.switch.locked { opacity: 0.65; cursor: not-allowed; }

.badge-warn { background: #fef3c7; color: #92400e; }

.save-card { padding: 14px 18px; }
.save-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.save-actions { display: flex; align-items: center; gap: 10px; }

.history { padding: 6px 18px 14px; display: flex; flex-direction: column; gap: 8px; }
.history-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  border: 1px solid #e6e9ed; border-radius: 10px; padding: 10px 12px;
}
.history-main { min-width: 0; }
.history-reason { margin-top: 3px; font-size: 12px; color: #4a5160; }
.history-paths { margin-top: 2px; font-size: 11px; color: #a6adbd; word-break: break-all; }

.warn-box {
  margin-bottom: 14px; background: #fffbeb; border: 1px solid #fde68a;
  color: #92400e; border-radius: 10px; padding: 10px 12px; font-size: 12px; line-height: 1.7;
}

.mcp-list { padding: 0 18px 14px; display: flex; flex-direction: column; gap: 8px; }
.mcp-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  border: 1px solid #e6e9ed; border-radius: 10px; padding: 10px 12px;
}
.mcp-main { min-width: 0; }
.mcp-name { font-size: 13px; font-weight: 600; color: #2f3033; display: flex; align-items: center; gap: 6px; }
.mcp-desc { margin-top: 3px; font-size: 11px; color: #a6adbd; word-break: break-all; }
.mcp-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.mcp-status { font-size: 11px; color: #a6adbd; }
.mcp-status.ok { color: #0f9f8f; }
.mcp-status.bad { color: #b42318; }
.mcp-form { border-top: 1px solid #eef0f3; padding: 14px 18px 16px; }
.mcp-form-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.mcp-form-grid .input, .mcp-form-grid .select { height: 34px; }
.mcp-form-grid .wide { flex: 1 1 320px; }
.mcp-check { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #4a5160; }
.mcp-form-hint { margin-top: 8px; font-size: 11px; color: #a6adbd; line-height: 1.7; }
.mcp-form-actions { margin-top: 10px; display: flex; justify-content: flex-end; gap: 8px; }
.empty { padding: 6px 0 2px; font-size: 12px; color: #a6adbd; }
.danger { color: #b42318; }
</style>
