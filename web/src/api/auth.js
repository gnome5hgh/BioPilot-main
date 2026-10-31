import axios from 'axios'
import { defineStore } from 'pinia'

const http = axios.create({ baseURL: '/api' })

/** 登录态存储：token 持久化到 localStorage（登出清除）。 */
export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('biopilot_token') || '',
    role: localStorage.getItem('biopilot_role') || '',
    nickName: localStorage.getItem('biopilot_nick') || '',
  }),
  actions: {
    async login(userName, password) {
      const { data } = await http.post('/auth/login', { userName, password })
      if (data.code !== 200) throw new Error(data.msg)
      this.token = data.data.token
      this.role = data.data.role
      this.nickName = data.data.nickName
      localStorage.setItem('biopilot_token', this.token)
      localStorage.setItem('biopilot_role', this.role)
      localStorage.setItem('biopilot_nick', this.nickName)
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
    },
  },
})

http.interceptors.request.use((cfg) => {
  const auth = useAuthStore()
  if (auth.token) cfg.headers['satoken'] = auth.token
  return cfg
})

export default http
