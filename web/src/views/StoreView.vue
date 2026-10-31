<template>
  <div class="store">
    <h2>专家 · 技能 · APP</h2>
    <div class="tabs">
      <button v-for="t in tabs" :key="t" :class="{ active: cur === t }" @click="cur = t">{{ t }}</button>
    </div>
    <div class="empty">商店页数据接入中（专家=agents / 技能=skills / APP 静态占位）。</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
const tabs = ['专家', '技能', 'APP']
const cur = ref('专家')
</script>

<style scoped>
.store { padding: 24px; }
.tabs { display: flex; gap: 12px; margin: 16px 0; }
.tabs button { border: none; background: #f8f9fc; border-radius: 8px; padding: 8px 16px; cursor: pointer; }
.tabs button.active { background: #2ec5b1; color: #fff; }
.empty { color: #a6adbd; font-size: 13px; padding: 40px 0; text-align: center; }
</style>
