import { defineStore } from 'pinia'
import http from '../api/auth'

/**
 * 对话页的共享状态：会话/项目列表、当前会话、消息与上下文用量。
 *
 * 放在 store 里的原因：左侧导航（MainLayout 里的 AppSidebar）与右侧对话区
 * （ChatView）都要读写同一份「当前在哪个会话/项目」，以前 ChatView 自己持有一份
 * 私有状态，导致侧栏点会话、新建任务、删除当前会话三处各写各的。
 */
export const useChatStore = defineStore('chat', {
  state: () => ({
    sessions: [],
    projects: [],
    models: [],
    selectedModel: '',
    currentId: '',
    currentProjectId: '',
    draftTitle: '',
    pendingPrompt: '',
    messages: [],
    usage: null,
    loadingHistory: false,
    loadingSessions: false,
    running: false,
    initialized: false,
  }),

  getters: {
    currentSession: (state) =>
      state.sessions.find((item) => item.agent_id === state.currentId) || null,
    currentTitle(state) {
      const session = this.currentSession
      if (session) return session.name || session.agent_id.slice(0, 8)
      return state.draftTitle || '新对话'
    },
    currentProject: (state) =>
      state.projects.find((item) => item.projectId === state.currentProjectId) || null,
    isDraft: (state) =>
      !state.sessions.some((item) => item.agent_id === state.currentId),
    ungroupedSessions: (state) =>
      state.sessions.filter((item) => !item.project_id),
    projectsWithSessions: (state) =>
      state.projects.map((project) => ({
        ...project,
        sessions: state.sessions.filter((item) => item.project_id === project.projectId),
      })),
  },

  actions: {
    /** 首次进入时并行拉取三份基础数据；没有当前会话就开一个空白草稿。 */
    async init() {
      await Promise.all([this.loadSessions(), this.loadProjects(), this.loadModels()])
      if (!this.currentId) this.newDraft()
      this.initialized = true
    },

    async loadSessions() {
      this.loadingSessions = true
      try {
        const { data } = await http.get('/sessions', { params: { limit: 200 } })
        this.sessions = data.data || []
      } catch {
        // 列表拿不到时保持已有数据，不把页面变成空
      } finally {
        this.loadingSessions = false
      }
    },

    async loadProjects() {
      try {
        const { data } = await http.get('/project')
        this.projects = data.data || []
      } catch {
        this.projects = []
      }
    },

    async loadModels() {
      try {
        const { data } = await http.get('/agent/models')
        this.models = data.models || []
        this.selectedModel = data.selected || data.models?.[0]?.name || ''
      } catch {
        this.models = []
      }
    },

    /**
     * 开一个空白草稿。projectId 为空表示不归属项目（发出去后进任务列表）。
     *
     * @param {string|null} projectId 归属项目
     */
    newDraft(projectId = null) {
      this.currentId = crypto.randomUUID()
      this.currentProjectId = projectId || ''
      this.draftTitle = ''
      this.messages = []
      this.usage = null
    },

    /**
     * 首条消息发出时先在本地登记会话行。
     *
     * 后端在 run 启动时才创建 bio_agent_state，而侧栏只在 run 结束时重拉列表；
     * 不先登记的话，整段 run 期间新会话在左栏（包括它所属的项目）不可见。
     * run 结束后 loadSessions 会用服务端行替换本行，标题以服务端自动标题为准。
     *
     * @param {string} task 用户本轮原话（标题取其前 20 字）
     */
    registerSession(task) {
      if (!this.currentId || !this.isDraft) return
      const name = (task || '').trim().replace(/\n/g, ' ').slice(0, 20)
      this.draftTitle = name
      this.sessions.unshift({
        agent_id: this.currentId,
        name,
        created_at: new Date().toISOString(),
        project_id: this.currentProjectId || null,
        message_count: 1,
      })
    },

    /**
     * 打开已有会话：拉历史消息与上下文用量。
     *
     * @param {object} session 会话行（agent_id/name/project_id/created_at）
     */
    async openSession(session) {
      if (!session?.agent_id) return
      this.currentId = session.agent_id
      this.currentProjectId = session.project_id || ''
      this.draftTitle = ''
      this.loadingHistory = true
      try {
        const { data } = await http.get('/agent/chat/history', {
          params: { conversationId: session.agent_id },
        })
        this.messages = (data.messages || []).map((message) => ({
          role: message.role,
          text: message.content || '',
          // 用户消息可能带本轮附件（后端回放时从 meta 取回），用于渲染文件卡片
          attachments: Array.isArray(message.attachments) ? message.attachments : [],
          reasoning: '',
          activity: [],
          streaming: false,
        }))
      } catch {
        this.messages = []
      } finally {
        this.loadingHistory = false
      }
      this.refreshUsage()
    },

    async refreshUsage() {
      if (!this.currentId) return
      try {
        const { data } = await http.get('/agent/chat/context-usage', {
          params: { conversationId: this.currentId },
        })
        this.usage = data.usage
      } catch {
        // 用量只是辅助信息，失败静默
      }
    },

    /** 删除会话；删的是当前会话时回到空白草稿（不保留项目归属）。 */
    async deleteSession(session) {
      await http.delete('/agent/chat/session', {
        params: { conversationId: session.agent_id },
      })
      this.sessions = this.sessions.filter((item) => item.agent_id !== session.agent_id)
      if (session.agent_id === this.currentId) {
        this.newDraft()
      }
    },

    async createProject(name) {
      const trimmed = (name || '').trim()
      if (!trimmed) return null
      const { data } = await http.post('/project', { name: trimmed })
      await this.loadProjects()
      return data.data
    },

    async renameProject(projectId, name) {
      await http.put(`/project/${projectId}`, { name })
      await this.loadProjects()
    },

    async deleteProject(projectId) {
      await http.delete(`/project/${projectId}`)
      this.projects = this.projects.filter((item) => item.projectId !== projectId)
      if (this.currentProjectId === projectId) this.currentProjectId = ''
      await this.loadSessions()
    },

    setDraftProject(projectId) {
      this.currentProjectId = projectId || ''
    },

    async selectModel(name) {
      this.selectedModel = name
      await http.post('/agent/models/select', { name })
    },
  },
})
