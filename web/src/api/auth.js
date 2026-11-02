import axios from 'axios'
import { defineStore } from 'pinia'

const http = axios.create({ baseURL: '/api/v1' })

/** 登录态存储：token 持久化到 localStorage（登出清除）。 */
export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('biopilot_token') || '',
    role: localStorage.getItem('biopilot_role') || '',
    nickName: localStorage.getItem('biopilot_nick') || '',
    userId: localStorage.getItem('biopilot_uid') || '',
  }),
  actions: {
    async login(userName, password) {
      const { data } = await http.post('/auth/login', { userName, password })
      if (data.code !== 200) throw new Error(data.msg)
      this.token = data.data.token
      this.role = data.data.role
      this.nickName = data.data.nickName
      this.userId = String(data.data.userId || '')
      localStorage.setItem('biopilot_token', this.token)
      localStorage.setItem('biopilot_role', this.role)
      localStorage.setItem('biopilot_nick', this.nickName)
      localStorage.setItem('biopilot_uid', this.userId)
      http.defaults.headers.common['satoken'] = this.token
    },
    async register(userName, password, nickName) {
      const { data } = await http.post('/auth/register', { userName, password, nickName })
      if (data.code !== 200) throw new Error(data.msg)
      return data.data
    },
    async logout() {
      try { await http.post('/auth/logout') } catch { /* token 已失效也清理 */ }
      this.token = ''
      localStorage.removeItem('biopilot_token')
      localStorage.removeItem('biopilot_role')
      localStorage.removeItem('biopilot_nick')
      localStorage.removeItem('biopilot_uid')
    },
  },
})

http.interceptors.request.use((cfg) => {
  const auth = useAuthStore()
  if (auth.token) cfg.headers['satoken'] = auth.token
  return cfg
})

// 401 统一跳登录：否则页面会把「登录态失效」当成空数据渲染（会话/文件全空），
// 用户看不出是掉登录了。登录页自身不跳，避免循环。
http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      localStorage.removeItem('biopilot_token')
      localStorage.removeItem('biopilot_role')
      localStorage.removeItem('biopilot_nick')
      localStorage.removeItem('biopilot_uid')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export default http
