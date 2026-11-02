<template>
  <div class="markdown" @click="onClick" v-html="html"></div>
</template>

<script setup>
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/common'
import 'highlight.js/styles/github.css'
import { toast } from '../utils/toast'

const props = defineProps({
  content: { type: String, default: '' },
})

const md = new MarkdownIt({
  html: false,          // 不信任模型输出里的原始 HTML
  linkify: true,
  breaks: true,
})

// 代码块带语言角标与复制按钮；复制走事件委托，避免把代码塞进属性里。
md.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx]
  const info = (token.info || '').trim()
  const lang = info.split(/\s+/)[0] || 'text'
  const code = token.content
  const highlighted = lang !== 'text' && hljs.getLanguage(lang)
    ? hljs.highlight(code, { language: lang }).value
    : md.utils.escapeHtml(code)
  return `<div class="code-wrap"><div class="code-head"><span>${md.utils.escapeHtml(lang)}</span>`
    + `<button type="button" class="code-copy">复制</button></div>`
    + `<pre class="code-block"><code class="hljs">${highlighted}</code></pre></div>`
}

// 外链统一新标签打开，不把当前会话带走。
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noreferrer noopener')
  return self.renderToken(tokens, idx, options)
}

const html = computed(() => md.render(props.content || ''))

async function onClick(event) {
  const button = event.target.closest?.('.code-copy')
  if (!button) return
  const code = button.closest('.code-wrap')?.querySelector('pre')?.textContent || ''
  try {
    await navigator.clipboard.writeText(code)
    toast('代码已复制', 'success', 1600)
  } catch {
    toast('复制失败，请手动选择文本', 'error')
  }
}
</script>

<style scoped>
.markdown { line-height: 1.75; font-size: 14px; word-break: break-word; }
.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  margin: 1.2em 0 0.5em;
  line-height: 1.35;
  font-weight: 700;
}
.markdown :deep(h1) { font-size: 1.45em; }
.markdown :deep(h2) { font-size: 1.25em; }
.markdown :deep(h3) { font-size: 1.1em; }
.markdown :deep(p) { margin: 0.6em 0; }
.markdown :deep(ul),
.markdown :deep(ol) { margin: 0.6em 0; padding-left: 1.4em; }
.markdown :deep(li) { margin: 0.25em 0; }
.markdown :deep(blockquote) {
  margin: 0.8em 0;
  padding: 6px 14px;
  border-left: 3px solid #bfeee7;
  background: #f7fdfc;
  color: #4a5160;
}
.markdown :deep(code) {
  background: #f2f4f7;
  border-radius: 4px;
  padding: 1px 5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.92em;
}
.markdown :deep(.code-wrap) {
  margin: 0.9em 0;
  border: 1px solid #e6e9ed;
  border-radius: 10px;
  overflow: hidden;
  background: #fbfcfd;
}
.markdown :deep(.code-head) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  border-bottom: 1px solid #e6e9ed;
  color: #818999;
  font-size: 11px;
  text-transform: lowercase;
}
.markdown :deep(.code-copy) {
  border: none;
  background: transparent;
  color: #2ec5b1;
  cursor: pointer;
  font-size: 11px;
}
.markdown :deep(.code-block) {
  margin: 0;
  padding: 12px 14px;
  overflow-x: auto;
  background: #fbfcfd;
}
.markdown :deep(.code-block code) {
  background: transparent;
  padding: 0;
  font-size: 12.5px;
  line-height: 1.65;
}
.markdown :deep(table) {
  border-collapse: collapse;
  margin: 0.8em 0;
  width: 100%;
  font-size: 13px;
}
.markdown :deep(th),
.markdown :deep(td) {
  border: 1px solid #e6e9ed;
  padding: 7px 10px;
  text-align: left;
  vertical-align: top;
}
.markdown :deep(th) { background: #f8f9fc; font-weight: 600; }
.markdown :deep(a) { color: #1f9e8c; text-decoration: underline; text-underline-offset: 2px; }
.markdown :deep(hr) { border: none; border-top: 1px solid #e6e9ed; margin: 1.2em 0; }
.markdown :deep(img) { max-width: 100%; border-radius: 8px; }
</style>
