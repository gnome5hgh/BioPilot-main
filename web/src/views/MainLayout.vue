<template>
  <div class="app">
    <!-- 左栏：导航 + 项目 + 任务列表（结构照 genpilot 原型；列表数据随项目/会话模块接入） -->
    <aside class="sidebar">
      <div class="brand-row">
        <span class="brand">BioPilot</span>
        <button class="ghost" @click="logout">退出</button>
      </div>
      <nav>
        <div class="nav-item" :class="{ active: $route.path === '/' }" @click="$router.push('/')">新建任务</div>
        <div class="nav-item" :class="{ active: $route.path === '/store' }" @click="$router.push('/store')">专家 · 技能 · APP</div>
        <div class="nav-item" :class="{ active: $route.path === '/scheduled' }" @click="$router.push('/scheduled')">定时任务</div>
      </nav>
      <div class="user-footer">
        <div class="avatar">{{ initial }}</div>
        <span>{{ auth.nickName || '用户' }}</span>
      </div>
    </aside>
    <!-- 中栏 + 右栏：各视图自行填充（对话/商店/定时任务页共用此布局壳） -->
    <main class="main"><router-view /></main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../api/auth'

const auth = useAuthStore()
const router = useRouter()
const initial = computed(() => (auth.nickName || 'U').slice(0, 1).toUpperCase())

async function logout() {
  await auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.app { display: flex; height: 100vh; min-width: 1080px; font-size: 14px; color: #2f3033; }
.sidebar { width: 260px; flex: none; background: #f8f9fc; border-right: 1px solid #e6e9ed; display: flex; flex-direction: column; }
.brand-row { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; }
.brand { font-size: 17px; font-weight: 700; }
.ghost { border: 1px solid #e6e9ed; background: #fff; border-radius: 6px; padding: 4px 10px; cursor: pointer; font-size: 12px; color: #818999; }
nav { flex: 1; padding: 4px 8px; }
.nav-item { padding: 10px 12px; border-radius: 8px; cursor: pointer; margin-bottom: 2px; }
.nav-item:hover { background: #f0f1f5; }
.nav-item.active { background: #eceef3; color: #2f3033; font-weight: 600; }
.user-footer { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-top: 1px solid #e6e9ed; }
.avatar { width: 26px; height: 26px; border-radius: 50%; background: #8fd9c8; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 12px; }
.main { flex: 1; background: #fff; overflow: auto; }
</style>
