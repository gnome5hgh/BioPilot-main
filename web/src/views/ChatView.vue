<template>
  <div class="chat">
    <div class="hero">BioPilot 你的科研智能搭档</div>
    <div class="cap-bar">
      <button v-for="(c, i) in caps" :key="c.name" class="cap" :class="{ active: i === curCap }" @click="curCap = i">
        {{ c.name }}
      </button>
    </div>
    <button class="example" @click="fillExample">{{ caps[curCap].example }}</button>
    <div class="input-card">
      <textarea v-model="input" :placeholder="placeholder" @keydown.enter.exact.prevent="send"></textarea>
      <div class="foot">
        <span class="hint">Enter 发送 · 产物经安全确认后落库</span>
        <button class="send" :disabled="busy" @click="send">{{ busy ? '…' : '发送' }}</button>
      </div>
    </div>
    <div class="messages">
      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <pre>{{ m.text }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
// 对话闭环：SSE 经 SpringBoot 转发到 Python 适配层；当前 send 为占位反馈，
// 真实流式链路接入后替换。
import { ref } from 'vue'

const caps = [
  { name: '生信分析', example: '示例：帮我整理单细胞 QC 的标准流程要点' },
  { name: '文献解析', example: '示例：帮我总结一篇论文的核心观点与图表结论' },
  { name: '知识解读', example: '示例：什么是单细胞测序技术？' },
  { name: '文档写作', example: '示例：帮我写一份空间组学的综述大纲' },
  { name: '平台搭建', example: '示例：帮我搭一个数据分析工具的静态展示页' },
]
const curCap = ref(0)
const input = ref('')
const busy = ref(false)
const messages = ref([])
const placeholder = '发送消息…（Enter 发送，Shift+Enter 换行）'

function fillExample() {
  input.value = caps.value[curCap.value].example.replace(/^示例：/, '')
}

function send() {
  // SSE 流接入前为占位反馈（保持可点性，不做禁用态）
  if (!input.value.trim() || busy.value) return
  messages.value.push({ role: 'user', text: input.value })
  messages.value.push({ role: 'assistant', text: '（演示）对话链路接入后此处为流式回答。' })
  input.value = ''
}
</script>

<style scoped>
.chat { padding: 40px 24px; max-width: 900px; margin: 0 auto; }
.hero { font-size: 34px; font-weight: 700; }
.cap-bar { display: flex; gap: 8px; margin: 24px 0 12px; flex-wrap: wrap; }
.cap { background: #f8f9fc; border: none; border-radius: 8px; padding: 8px 12px; cursor: pointer; font-size: 13px; }
.cap.active { background: #2ec5b1; color: #fff; }
.example { display: block; width: 100%; text-align: left; border: 1px solid #e6e9ed; border-radius: 10px; padding: 11px 14px; background: #fff; cursor: pointer; font-size: 13px; color: #818999; }
.input-card { border: 1px solid #e6e9ed; border-radius: 14px; padding: 12px 14px; margin-top: 16px; }
textarea { width: 100%; min-height: 54px; border: none; resize: none; font-size: 14px; outline: none; }
.foot { display: flex; justify-content: space-between; align-items: center; }
.hint { font-size: 12px; color: #a6adbd; }
.send { background: #2ec5b1; color: #fff; border: none; border-radius: 50%; width: 34px; height: 34px; cursor: pointer; }
.messages { margin-top: 24px; display: flex; flex-direction: column; gap: 12px; }
.msg pre { white-space: pre-wrap; font-family: inherit; margin: 0; padding: 12px 14px; border-radius: 10px; font-size: 14px; }
.msg.user pre { background: #e8f8f5; }
.msg.assistant pre { background: #f8f9fc; }
</style>
