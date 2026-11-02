<template>
  <div class="app">
    <AppSidebar />
    <main class="main"><router-view /></main>
    <TerminalPanel v-if="terminalMounted" />
  </div>
</template>

<script setup>
import { defineAsyncComponent, ref, watch } from 'vue'
import AppSidebar from '../components/AppSidebar.vue'
import { useTerminalStore } from '../stores/terminal'

// 终端面板首次打开才挂载并加载 xterm；之后一直保留（关闭只是隐藏），
// 这样切换会话不会重建终端实例，也不会把 xterm 打进首屏包。
const TerminalPanel = defineAsyncComponent(() => import('../components/TerminalPanel.vue'))
const terminal = useTerminalStore()
const terminalMounted = ref(false)

watch(() => terminal.open, (open) => {
  if (open) terminalMounted.value = true
}, { immediate: true })
</script>

<style scoped>
.app {
  display: flex;
  height: 100vh;
  min-width: 960px;
  overflow: hidden;
}
.main {
  flex: 1;
  min-width: 0;
  background: #fff;
  overflow: auto;
}
</style>
