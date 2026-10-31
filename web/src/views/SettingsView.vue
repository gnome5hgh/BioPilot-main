<template>
  <div class="settings">
    <h2>设置</h2>
    <div class="row">
      <span>意图识别</span>
      <button :class="{ on: intentEnabled }" @click="intentEnabled = !intentEnabled">
        {{ intentEnabled ? '开' : '关' }}
      </button>
    </div>
    <div class="row dep" v-if="intentEnabled">
      <span>Jev 判定服务（意图识别依赖）</span>
      <span class="hint">配置在 config.yaml intent.jev 段</span>
    </div>
    <div class="row">
      <span>确认档位（confirm_above）</span>
      <select v-model="confirmAbove">
        <option>low</option><option>medium</option><option>high</option>
      </select>
    </div>
    <button class="save" @click="save">保存（下一个 run 生效）</button>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import http from '../api/auth'

const intentEnabled = ref(false)
const confirmAbove = ref('medium')

onMounted(async () => {
  const r = await http.get('/agent/settings')
  intentEnabled.value = r.data.intent_enabled
  confirmAbove.value = r.data.confirm_above
})

async function save() {
  await http.post('/agent/settings', {
    intent_enabled: intentEnabled.value,
    confirm_above: confirmAbove.value,
  })
}
</script>

<style scoped>
.settings { padding: 24px; max-width: 560px; }
.row { display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #e6e9ed; }
.row.dep { padding-left: 20px; color: #818999; font-size: 13px; }
.row button { border: none; border-radius: 12px; padding: 4px 16px; cursor: pointer; background: #f0f1f5; color: #818999; }
.row button.on { background: #2ec5b1; color: #fff; }
select { border: 1px solid #e6e9ed; border-radius: 6px; padding: 4px 10px; }
.save { background: #2ec5b1; color: #fff; border: none; border-radius: 8px; padding: 10px 24px; cursor: pointer; margin-top: 16px; }
.hint { font-size: 12px; }
h2 { margin: 0 0 8px; }
</style>
