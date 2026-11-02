<template>
  <div class="page settings">
    <div class="page-head">
      <div>
        <h2 class="page-title">设置</h2>
        <p class="page-sub">这里的改动在下一轮对话开始时生效，不影响正在运行的会话。</p>
      </div>
    </div>

    <section class="card section">
      <div class="row">
        <div class="row-main">
          <div class="row-title">意图识别</div>
          <div class="row-desc">只作为提示信号注入对话，不改变派发与执行；开启后每轮多一次分类开销。</div>
        </div>
        <button class="switch" :class="{ on: intentEnabled }" @click="intentEnabled = !intentEnabled">
          {{ intentEnabled ? '开' : '关' }}
        </button>
      </div>
      <div v-if="intentEnabled" class="hint">
        Jev 判定服务的端点与密钥在 config.yaml 的 intent.jev 段配置。
      </div>
    </section>

    <section class="card section">
      <div class="row">
        <div class="row-main">
          <div class="row-title">安全确认档位</div>
          <div class="row-desc">决定哪些工具调用会弹出确认框。档位越高，系统询问得越少。</div>
        </div>
        <select v-model="confirmAbove" class="select">
          <option value="low">严格（中风险及以上都问）</option>
          <option value="medium">标准（高风险及以上才问）</option>
          <option value="high">宽松（仅严重风险询问）</option>
        </select>
      </div>
      <div class="levels">
        <div class="level" :class="{ active: confirmAbove === 'low' }">
          <b>严格</b>
          <span>写文件、执行分析代码、读取论文等都会先问你一次。最安全，但打断最多。</span>
        </div>
        <div class="level" :class="{ active: confirmAbove === 'medium' }">
          <b>标准</b>
          <span>只有高风险工具会问；日常读文件、检索、写文档不打断。</span>
        </div>
        <div class="level" :class="{ active: confirmAbove === 'high' }">
          <b>宽松</b>
          <span>只有严重风险才问。当前工具集里几乎没有这一档，等于基本不弹确认。</span>
        </div>
      </div>
      <div v-if="confirmAbove === 'high'" class="warn-box">
        当前档位下写文件、执行代码等操作将静默执行。除非你明确知道风险，否则建议用「标准」。
      </div>
    </section>

    <button class="btn btn-primary save" :disabled="saving" @click="save">
      {{ saving ? '保存中…' : '保存设置' }}
    </button>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import http from '../api/auth'
import { errText } from '../utils/errors'
import { toast } from '../utils/toast'

const intentEnabled = ref(false)
const confirmAbove = ref('medium')
const saving = ref(false)

onMounted(load)

async function load() {
  try {
    const { data } = await http.get('/agent/settings')
    intentEnabled.value = Boolean(data.intent_enabled)
    confirmAbove.value = data.confirm_above || 'medium'
  } catch (error) {
    toast(errText(error, '设置读取失败'), 'error')
  }
}

async function save() {
  saving.value = true
  try {
    await http.post('/agent/settings', {
      intent_enabled: intentEnabled.value,
      confirm_above: confirmAbove.value,
    })
    toast('设置已保存，下一轮对话生效', 'success')
  } catch (error) {
    toast(errText(error, '保存失败'), 'error')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.settings { max-width: 760px; }
.section { margin-bottom: 16px; padding: 0; overflow: hidden; }
.row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 16px 18px;
}
.row-main { min-width: 0; }
.row-title { font-size: 14px; font-weight: 600; }
.row-desc { margin-top: 4px; font-size: 12px; color: #818999; line-height: 1.7; }
.hint { padding: 0 18px 14px; font-size: 12px; color: #a6adbd; }

.switch {
  flex: none;
  border: none;
  border-radius: 999px;
  padding: 5px 16px;
  background: #f0f1f5;
  color: #818999;
  cursor: pointer;
  font-size: 12px;
}
.switch.on { background: #2ec5b1; color: #fff; }

.levels {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding: 0 18px 16px;
}
.level {
  border: 1px solid #e6e9ed;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 11px;
  color: #818999;
  line-height: 1.7;
}
.level b { display: block; margin-bottom: 3px; color: #4a5160; font-size: 12px; }
.level.active { border-color: #2ec5b1; background: #f3fdfa; }

.warn-box {
  margin: 0 18px 16px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  color: #92400e;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.7;
}

.save { margin-top: 8px; }
</style>
