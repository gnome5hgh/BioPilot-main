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
      { path: 'scheduled', component: () => import('../views/ScheduledView.vue') },
      { path: 'admin', component: () => import('../views/AdminView.vue'),
        meta: { roles: ['ADMIN'] } },
      { path: 'papers', component: () => import('../views/PapersView.vue') },
      // 文档编辑器已并入文件管理（/papers）；旧路径重定向保持收藏夹不落空
      { path: 'docs', redirect: '/papers' },
      { path: 'literature', component: () => import('../views/LiteratureView.vue') },
      { path: 'citations', component: () => import('../views/CitationsView.vue') },
      { path: 'terminal', redirect: '/' },
      { path: 'settings', component: () => import('../views/SettingsView.vue'),
        meta: { roles: ['ADMIN'] } },
      { path: 'kb', component: () => import('../views/KBView.vue') },
      { path: 'skills', component: () => import('../views/SkillsView.vue') },
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
