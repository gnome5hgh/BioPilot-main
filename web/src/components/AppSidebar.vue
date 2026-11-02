<template>
  <aside class="sidebar">
    <div class="brand-row">
      <span class="brand">BioPilot</span>
      <span class="brand-sub">科研智能搭档</span>
    </div>

    <button class="new-chat" @click="startDraft(null)">
      <span class="plus">＋</span> 新对话
    </button>

    <div class="search-row">
      <input v-model="query" class="search" placeholder="搜索会话或项目" />
    </div>

    <div class="scroll">
      <section class="list-section">
        <div class="section-head">
          <span>任务列表</span>
          <span class="count">{{ store.ungroupedSessions.length }}</span>
        </div>
        <template v-for="group in ungroupedGroups" :key="group.label">
          <div class="sub-label">{{ group.label }}</div>
          <button v-for="session in group.items" :key="session.agent_id"
                  class="session-item" :class="{ active: session.agent_id === store.currentId }"
                  @click="openSession(session)">
            <span class="name">{{ sessionName(session) }}</span>
            <span class="time">{{ fmtTimeOrDate(session.created_at) }}</span>
            <span class="more" role="button" tabindex="0" title="会话操作"
                  @click.stop="openSessionMenu(session, $event)"
                  @keydown.enter.stop="openSessionMenu(session, $event)">⋯</span>
          </button>
        </template>
        <div v-if="!store.ungroupedSessions.length" class="empty-mini">
          还没有任务。直接发送消息，会话会出现在这里。
        </div>
      </section>

      <section class="list-section">
        <div class="section-head">
          <span>项目</span>
          <button class="mini" title="新建项目" @click="startCreateProject">＋</button>
        </div>
        <div v-if="creatingProject" class="create-row">
          <input ref="createInput" v-model="newProjectName" placeholder="项目名称，回车创建"
                 @keydown.enter.prevent="createProject" @keydown.esc="creatingProject = false" />
        </div>
        <div v-for="project in visibleProjects" :key="project.projectId" class="project-block">
          <div class="project-row" :class="{ selected: project.projectId === store.currentProjectId }">
            <button class="chev" :aria-label="showSessions(project.projectId) ? '收起' : '展开'"
                    @click="toggleProject(project.projectId)">
              {{ showSessions(project.projectId) ? '▾' : '▸' }}
            </button>
            <input v-if="renamingId === project.projectId" v-model="renameValue"
                   class="rename-input" @keydown.enter.prevent="saveRename(project)"
                   @keydown.esc="renamingId = ''" @blur="saveRename(project)" />
            <button v-else class="project-name" @click="toggleProject(project.projectId)">
              📁 {{ project.name }}
            </button>
            <span class="count">{{ project.sessions.length }}</span>
            <button class="mini" title="在此项目下新建会话"
                    @click="startDraft(project.projectId)">＋</button>
            <button class="mini" title="项目操作"
                    @click.stop="openProjectMenu(project, $event)">⋯</button>
          </div>
          <template v-if="showSessions(project.projectId)">
            <button v-for="session in project.sessions" :key="session.agent_id"
                    class="session-item sub" :class="{ active: session.agent_id === store.currentId }"
                    @click="openSession(session)">
              <span class="name">{{ sessionName(session) }}</span>
              <span class="time">{{ fmtTimeOrDate(session.created_at) }}</span>
              <span class="more" role="button" tabindex="0" title="会话操作"
                    @click.stop="openSessionMenu(session, $event)"
                    @keydown.enter.stop="openSessionMenu(session, $event)">⋯</span>
            </button>
            <div v-if="!project.sessions.length" class="empty-mini">暂无会话</div>
          </template>
        </div>
        <div v-if="!store.projects.length" class="empty-mini">
          还没有项目。项目用来把同一课题的会话和文件归在一起。
        </div>
      </section>
    </div>

    <nav class="nav" aria-label="功能导航">
      <button v-for="item in navItems" :key="item.path" class="nav-item"
              :class="{ active: isActive(item.path) }" @click="go(item.path)">
        <span class="nav-icon" aria-hidden="true">{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <div class="user-footer">
      <div class="avatar">{{ initial }}</div>
      <span class="user-name">{{ auth.nickName || '用户' }}</span>
      <button class="footer-icon" title="打开终端（会话会保留）" aria-label="打开终端"
              @click="terminal.toggle()">&gt;_</button>
      <button class="btn btn-sm logout" @click="logout">退出</button>
    </div>

    <template v-if="menu.open">
      <div class="menu-mask" @click="closeMenu"></div>
      <div class="menu-pop" :style="{ left: menu.x + 'px', top: menu.y + 'px' }">
        <button v-if="menu.kind === 'project'" class="menu-item"
                @click="beginRename(menu.item)">重命名项目</button>
        <button v-if="menu.kind === 'project'" class="menu-item"
                @click="startDraft(menu.item.projectId)">在此项目下新建会话</button>
        <button class="menu-item danger" @click="removeMenuTarget">
          {{ menu.kind === 'project' ? '删除项目' : '删除会话' }}
        </button>
      </div>
    </template>
  </aside>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../api/auth'
import { useChatStore } from '../stores/chat'
import { useTerminalStore } from '../stores/terminal'
import { confirmDialog } from '../utils/confirm'
import { errText } from '../utils/errors'
import { toast } from '../utils/toast'
import { fmtTimeOrDate, parseTime } from '../utils/time'

const auth = useAuthStore()
const store = useChatStore()
const terminal = useTerminalStore()
const router = useRouter()
const route = useRoute()

const query = ref('')
const expanded = reactive(new Set())
const creatingProject = ref(false)
const newProjectName = ref('')
const createInput = ref(null)
const renamingId = ref('')
const renameValue = ref('')

const menu = reactive({ open: false, kind: '', item: null, x: 0, y: 0 })

const navItems = computed(() => {
  const items = [
    { path: '/store', label: '技能', icon: '✦' },
    { path: '/scheduled', label: '定时任务', icon: '◷' },
    { path: '/papers', label: '文件管理', icon: '▤' },
    { path: '/literature', label: '文献搜索', icon: '⌕' },
    { path: '/kb', label: '知识库', icon: '◈' },
    { path: '/citations', label: '引用库', icon: '❝' },
  ]
  if (auth.role === 'ADMIN') {
    items.push({ path: '/admin', label: '管理端', icon: '☰' })
    items.push({ path: '/settings', label: '设置', icon: '⚙' })
  }
  return items
})

const initial = computed(() => (auth.nickName || 'U').slice(0, 1).toUpperCase())

const visibleProjects = computed(() => {
  const text = query.value.trim().toLowerCase()
  if (!text) return store.projectsWithSessions
  return store.projectsWithSessions.filter((project) =>
    project.name.toLowerCase().includes(text)
    || project.sessions.some((session) => sessionName(session).toLowerCase().includes(text)))
})

const ungroupedGroups = computed(() => {
  const text = query.value.trim().toLowerCase()
  const items = store.ungroupedSessions.filter((session) =>
    !text || sessionName(session).toLowerCase().includes(text))
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1)
  const groups = { 今天: [], 昨天: [], 更早: [] }
  for (const session of items) {
    const created = parseTime(session.created_at)
    if (!created || created >= today) groups.今天.push(session)
    else if (created >= yesterday) groups.昨天.push(session)
    else groups.更早.push(session)
  }
  return Object.entries(groups)
    .filter(([, list]) => list.length)
    .map(([label, list]) => ({ label, items: list }))
})

function sessionName(session) {
  return session.name || session.agent_id.slice(0, 8)
}

function isActive(path) {
  return route.path === path
}

function go(path) {
  router.push(path)
}

async function startDraft(projectId) {
  if (store.running) {
    toast('当前回答还在进行，请先中断再切换会话', 'error')
    return
  }
  store.newDraft(projectId)
  if (projectId) expanded.add(projectId)
  closeMenu()
  if (route.path !== '/') await router.push('/')
}

async function openSession(session) {
  if (store.running) {
    toast('当前回答还在进行，请先中断再切换会话', 'error')
    return
  }
  await store.openSession(session)
  closeMenu()
  if (route.path !== '/') await router.push('/')
}

function toggleProject(projectId) {
  if (expanded.has(projectId)) expanded.delete(projectId)
  else expanded.add(projectId)
}

// 搜索命中项目里的会话时自动展开，否则结果会被折叠状态藏起来
function showSessions(projectId) {
  return expanded.has(projectId) || Boolean(query.value.trim())
}

async function startCreateProject() {
  creatingProject.value = true
  await nextTick()
  createInput.value?.focus()
}

async function createProject() {
  const name = newProjectName.value.trim()
  if (!name) return
  try {
    const project = await store.createProject(name)
    newProjectName.value = ''
    creatingProject.value = false
    if (project?.projectId) expanded.add(project.projectId)
    toast('项目已创建', 'success')
  } catch (error) {
    toast(errText(error, '新建项目失败'), 'error')
  }
}

function beginRename(project) {
  closeMenu()
  renamingId.value = project.projectId
  renameValue.value = project.name
}

async function saveRename(project) {
  if (renamingId.value !== project.projectId) return
  const name = renameValue.value.trim()
  renamingId.value = ''
  if (!name || name === project.name) return
  try {
    await store.renameProject(project.projectId, name)
    toast('项目已重命名', 'success')
  } catch (error) {
    toast(errText(error, '重命名失败'), 'error')
  }
}

function openSessionMenu(session, event) {
  const rect = event?.currentTarget?.getBoundingClientRect?.()
  const x = rect ? Math.min(rect.right - 8, window.innerWidth - 180) : event.clientX
  const y = rect ? rect.bottom + 4 : event.clientY
  Object.assign(menu, { open: true, kind: 'session', item: session, x, y })
}

function openProjectMenu(project, event) {
  const rect = event?.currentTarget?.getBoundingClientRect?.()
  const x = rect ? Math.min(rect.right - 8, window.innerWidth - 190) : event.clientX
  const y = rect ? rect.bottom + 4 : event.clientY
  Object.assign(menu, { open: true, kind: 'project', item: project, x, y })
}

function closeMenu() {
  menu.open = false
  menu.kind = ''
  menu.item = null
}

async function removeMenuTarget() {
  const kind = menu.kind
  const item = menu.item
  closeMenu()
  if (!item) return
  if (kind === 'session') {
    const ok = await confirmDialog({
      title: '删除会话',
      message: `删除「${sessionName(item)}」及其全部消息？`,
      detail: '删除后不可恢复；文件与知识库不受影响。',
      confirmText: '删除',
      danger: true,
    })
    if (!ok) return
    try {
      await store.deleteSession(item)
      toast('会话已删除', 'success')
    } catch (error) {
      toast(errText(error, '删除会话失败'), 'error')
    }
    return
  }
  const ok = await confirmDialog({
    title: '删除项目',
    message: `删除项目「${item.name}」？`,
    detail: '项目下的会话不会删除，会回到任务列表。',
    confirmText: '删除项目',
    danger: true,
  })
  if (!ok) return
  try {
    await store.deleteProject(item.projectId)
    toast('项目已删除，会话已回到任务列表', 'success')
  } catch (error) {
    toast(errText(error, '删除项目失败'), 'error')
  }
}

async function logout() {
  await auth.logout()
  router.push('/login')
}

onMounted(async () => {
  await store.init()
  // 默认展开有会话的项目与当前项目，避免用户进来看到一排折叠行
  for (const project of store.projects) {
    if (project.projectId === store.currentProjectId
      || store.sessions.some((session) => session.project_id === project.projectId)) {
      expanded.add(project.projectId)
    }
  }
})
</script>

<style scoped>
.sidebar {
  width: 288px;
  flex: none;
  background: #f8f9fc;
  border-right: 1px solid #e6e9ed;
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.brand-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 16px 18px 10px;
}

.brand { font-size: 18px; font-weight: 800; letter-spacing: 0.2px; }
.brand-sub { font-size: 11px; color: #a6adbd; }

.new-chat {
  margin: 0 14px 10px;
  border: 1px solid #d9eee9;
  background: #fff;
  color: #1f9e8c;
  border-radius: 10px;
  padding: 9px 12px;
  text-align: left;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.new-chat:hover { border-color: #2ec5b1; background: #f3fdfa; }
.plus { margin-right: 6px; }

.search-row { padding: 0 14px 8px; }
.search {
  width: 100%;
  height: 32px;
  border: 1px solid #e6e9ed;
  border-radius: 8px;
  padding: 0 10px;
  font-size: 12px;
  background: #fff;
  outline: none;
}
.search:focus { border-color: #2ec5b1; }

.scroll { flex: 1; overflow-y: auto; padding: 2px 8px 8px; }

.list-section { margin-bottom: 6px; }
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 8px 4px;
  font-size: 11px;
  color: #a6adbd;
  letter-spacing: 0.4px;
}
.count { font-size: 11px; color: #b7bdc9; }
.sub-label { font-size: 11px; color: #b7bdc9; padding: 6px 10px 2px; }

.mini {
  border: none;
  background: transparent;
  color: #2ec5b1;
  cursor: pointer;
  font-size: 13px;
  padding: 0 4px;
  border-radius: 4px;
}
.mini:hover { background: #e8f8f5; }

.session-item {
  width: 100%;
  border: none;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 9px;
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  color: #4a5160;
}
.session-item:hover { background: #f0f1f5; }
.session-item.active { background: #e8f8f5; }
.session-item.active .name { color: #1f9e8c; font-weight: 600; }
.session-item.sub { padding-left: 22px; }
.name { flex: 1; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.time { flex: none; font-size: 11px; color: #b7bdc9; }
.more {
  flex: none;
  font-size: 13px;
  color: #a6adbd;
  padding: 0 3px;
  border-radius: 4px;
  visibility: hidden;
}
.session-item:hover .more, .session-item:focus-within .more { visibility: visible; }

.project-block { margin-bottom: 2px; }
.project-row {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 6px 6px 6px 2px;
  border-radius: 8px;
}
.project-row:hover { background: #f0f1f5; }
.project-row.selected { background: #eefbf8; }
.chev {
  border: none;
  background: transparent;
  color: #a6adbd;
  cursor: pointer;
  width: 18px;
  font-size: 11px;
}
.project-name {
  flex: 1;
  border: none;
  background: transparent;
  text-align: left;
  font-size: 13px;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 2px 0;
  color: #4a5160;
}
.project-row.selected .project-name { color: #1f9e8c; font-weight: 600; }
.rename-input {
  flex: 1;
  border: 1px solid #2ec5b1;
  border-radius: 6px;
  padding: 3px 6px;
  font-size: 12px;
  outline: none;
}
.create-row { padding: 2px 8px 6px; }
.create-row input {
  width: 100%;
  border: 1px solid #2ec5b1;
  border-radius: 8px;
  padding: 6px 9px;
  font-size: 12px;
  outline: none;
}
.empty-mini { font-size: 11px; color: #b7bdc9; padding: 6px 12px 10px; line-height: 1.6; }

.nav {
  flex: none;
  border-top: 1px solid #e6e9ed;
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  border: none;
  background: transparent;
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 12.5px;
  color: #4a5160;
  cursor: pointer;
  text-align: left;
}
.nav-item:hover { background: #f0f1f5; }
.nav-item.active { background: #e8f8f5; color: #1f9e8c; font-weight: 600; }
.nav-icon { width: 16px; text-align: center; color: #a6adbd; font-size: 12px; }
.nav-item.active .nav-icon { color: #2ec5b1; }

.user-footer {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid #e6e9ed;
}
.avatar {
  width: 26px; height: 26px; border-radius: 50%; background: #8fd9c8; color: #fff;
  display: flex; align-items: center; justify-content: center; font-size: 12px;
}
.user-name { flex: 1; font-size: 12px; color: #4a5160; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.footer-icon {
  border: 1px solid #e6e9ed;
  background: #fff;
  border-radius: 7px;
  color: #4a5160;
  cursor: pointer;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 11px;
  padding: 3px 7px;
}
.footer-icon:hover { border-color: #2ec5b1; color: #1f9e8c; }
.logout { padding: 3px 8px; }

.menu-mask { position: fixed; inset: 0; z-index: 60; }
.menu-pop {
  position: fixed;
  z-index: 61;
  min-width: 156px;
  background: #fff;
  border: 1px solid #e6e9ed;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(20, 24, 34, 0.12);
  padding: 4px;
}
.menu-item {
  display: block;
  width: 100%;
  border: none;
  background: transparent;
  text-align: left;
  padding: 8px 10px;
  font-size: 12px;
  border-radius: 6px;
  cursor: pointer;
  color: #4a5160;
}
.menu-item:hover { background: #f8f9fc; }
.menu-item.danger { color: #e5484d; }
</style>
