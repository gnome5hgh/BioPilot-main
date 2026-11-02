import { defineStore } from 'pinia'

/**
 * 全局终端面板状态：整个应用只有一块面板、一条会话。
 *
 * 面板在 MainLayout 里常驻挂载，关闭只是隐藏；因此切换会话/页面都不会重建
 * xterm 实例，服务端也按 user_id 复用同一条 shell。
 */
export const useTerminalStore = defineStore('terminal', {
  state: () => ({
    open: false,
    enabled: true,
    shell: 'zsh',
  }),
  actions: {
    toggle() {
      this.open = !this.open
    },
    show() {
      this.open = true
    },
    hide() {
      this.open = false
    },
    setConfig(config) {
      this.enabled = Boolean(config?.enabled)
      this.shell = config?.shell || 'sh'
    },
  },
})
