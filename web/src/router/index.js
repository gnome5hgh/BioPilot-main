import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../api/auth'

// 路由守卫：未登录访问受保护页 → 跳登录（工单 09 验收项）
const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue') },
  {
    path: '/',
    component: () => import('../views/MainLayout.vue'),
    children: [
      { path: '', component: () => import('../views/ChatView.vue') },
      { path: 'store', component: () => import('../views/StoreView.vue') },
      { path: 'scheduled', component: () => import('../views/ScheduledView.vue') },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path !== '/login' && !auth.token) return '/login'
})

export default router
