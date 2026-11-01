import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../api/auth'

// 路由守卫：未登录访问受保护页 → 跳登录
const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue') },
  {
    path: '/',
    component: () => import('../views/MainLayout.vue'),
    children: [
      { path: '', component: () => import('../views/ChatView.vue') },
      { path: 'store', component: () => import('../views/StoreView.vue') },
      { path: 'scheduled', component: () => import('../views/ScheduledView.vue') },
      { path: 'admin', component: () => import('../views/AdminView.vue'),
        meta: { roles: ['ADMIN'] } },
      { path: 'papers', component: () => import('../views/PapersView.vue') },
      { path: 'docs', component: () => import('../views/DocEditorView.vue') },
      { path: 'literature', component: () => import('../views/LiteratureView.vue') },
      { path: 'terminal', component: () => import('../views/TerminalView.vue') },
      { path: 'settings', component: () => import('../views/SettingsView.vue'),
        meta: { roles: ['ADMIN'] } },
      { path: 'kb', component: () => import('../views/KBView.vue') },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

// 路由守卫（照 RBAC 三层的前端层）：①未登录访问受保护页 → 跳登录；
// ②声明了 meta.roles 的路由按登录角色裁决——直接敲 URL 也进不去，
// 与侧栏 v-if（导航层）和后端 @SaCheckRole（接口层）三层设防
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path !== '/login' && !auth.token) return '/login'
  const roles = to.meta.roles
  if (roles && !roles.includes(auth.role)) return '/'
})

export default router
