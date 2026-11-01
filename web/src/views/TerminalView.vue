<template>
  <div class="term">
    <div class="note">终端视图：连接本地 PTY 跑 biopilot REPL（WebSocket 端点在适配层）。</div>
    <div class="term-body" ref="termBox"></div>
  </div>
</template>

<script setup>
// xterm.js + WebSocket 桥接待接；当前为视图占位
const termBox = ref(null)
</script>

<style scoped>
.term { padding: 12px; height: 100%; }
.term-body { background: #262626; color: #d6d6d6; font-family: monospace; height: 80vh; border-radius: 10px; padding: 12px; }
.note { font-size: 12px; color: #a6adbd; margin-bottom: 8px; }
</style>
