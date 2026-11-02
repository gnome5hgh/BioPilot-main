<template>
  <div class="page settings">
    <div class="page-head">
      <div>
        <h2 class="page-title">设置</h2>
        <p class="page-sub">这里的改动在下一轮对话开始时生效，不影响正在运行的会话。</p>
      </div>
    </div>

    <section class="card section">
      <div class="row">
        <div class="row-main">
          <div class="row-title">意图识别</div>
          <div class="row-desc">只作为提示信号注入对话，不改变派发与执行；开启后每轮多一次分类开销。</div>
        </div>
        <button class="switch" :class="{ on: intentEnabled }" @click="intentEnabled = !intentEnabled">
          {{ intentEnabled ? '开' : '关' }}
        </button>
      </div>
      <div v-if="intentEnabled" class="hint">
        Jev 判定服务的端点与密钥在 config.yaml 的 intent.jev 段配置。
      </div>
    </section>

    <section class="card section">
      <div class="row">
        <div class="row-main">
          <div class="row-title">安全确认档位</div>
          <div class="row-desc">决定哪些工具调用会弹出确认框。档位越高，系统询问得越少。</div>
        </div>
        <select v-model="confirmAbove" class="select">
          <option value="low">严格（中风险及以上都问）</option>
          <option value="medium">标准（高风险及以上才问）</option>
          <option value="high">宽松（仅严重风险询问）</option>
        </select>
      </div>
      <div class="levels">
        <div class="level" :class="{ active: confirmAbove === 'low' }">
          <b>严格</b>
          <span>写文件、执行分析代码、读取论文等都会先问你一次。最安全，但打断最多。</span>
        </div>
        <div class="level" :class="{ active: confirmAbove === 'medium' }">
          <b>标准</b>
          <span>只有高风险工具会问；日常读文件、检索、写文档不打断。</span>
        </div>
        <div class="level" :class="{ active: confirmAbove === 'high' }">
          <b>宽松</b>
          <span>只有严重风险才问。当前工具集里几乎没有这一档，等于基本不弹确认。</span>
        </div>
      </div>
      <div v-if="confirmAbove === 'high'" class="warn-box">
        当前档位下写文件、执行代码等操作将静默执行。除非你明确知道风险，否则建议用「标准」。
      </div>
    </section>

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

    <button class="btn btn-primary save" :disabled="saving" @click="save">
      {{ saving ? '保存中…' : '保存设置' }}
    </button>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import http from '../api/auth'
import { errText } from '../utils/errors'
import { toast } from '../utils/toast'

const intentEnabled = ref(false)
const confirmAbove = ref('medium')
const saving = ref(false)

const mcpServers = ref([])
const mcpStatuses = ref({})
const mcpSaving = ref(false)
const mcpForm = reactive({
  open: false,
  id: '',
  name: '',
  transport: 'http',
  url: '',
  command: '',
  allowedTools: 'search_papers',
  enabled: true,
})

onMounted(load)

async function load() {
  try {
    const { data } = await http.get('/admin/settings')
    intentEnabled.value = Boolean(data.intent_enabled)
    confirmAbove.value = data.confirm_above || 'medium'
  } catch (error) {
    toast(errText(error, '设置读取失败'), 'error')
  }
  await Promise.all([loadMcp(), loadMcpStatus()])
}

async function save() {
  saving.value = true
  try {
    await http.patch('/admin/settings', {
      intent_enabled: intentEnabled.value,
      confirm_above: confirmAbove.value,
    })
    toast('设置已保存，下一轮对话生效', 'success')
  } catch (error) {
    toast(errText(error, '保存失败'), 'error')
  } finally {
    saving.value = false
  }
}

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
    open: true,
    id: '',
    name: '',
    transport: 'http',
    url: 'http://127.0.0.1:8000/mcp',
    command: '',
    allowedTools: 'search_papers',
    enabled: true,
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
    disabledTools: [],
    enabled: mcpForm.enabled,
  }
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
  if (!window.confirm(`删除检索源 ${server.name}？`)) return
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
.settings { max-width: 860px; }
.section { margin-bottom: 16px; padding: 0; overflow: hidden; }
.row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 16px 18px;
}
.row-main { min-width: 0; }
.row-title { font-size: 14px; font-weight: 600; }
.row-desc { margin-top: 4px; font-size: 12px; color: #818999; line-height: 1.7; }
.hint { padding: 0 18px 14px; font-size: 12px; color: #a6adbd; }

.switch {
  flex: none;
  border: none;
  border-radius: 999px;
  padding: 5px 16px;
  background: #f0f1f5;
  color: #818999;
  cursor: pointer;
  font-size: 12px;
}
.switch.on { background: #2ec5b1; color: #fff; }

.levels {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding: 0 18px 16px;
}
.level {
  border: 1px solid #e6e9ed;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 11px;
  color: #818999;
  line-height: 1.7;
}
.level b { display: block; margin-bottom: 3px; color: #4a5160; font-size: 12px; }
.level.active { border-color: #2ec5b1; background: #f3fdfa; }

.warn-box {
  margin: 0 18px 16px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  color: #92400e;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.7;
}

.mcp-list { padding: 0 18px 14px; display: flex; flex-direction: column; gap: 8px; }
.mcp-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid #e6e9ed;
  border-radius: 10px;
  padding: 10px 12px;
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
.save { margin-top: 8px; }
</style>
