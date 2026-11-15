<template>
  <aside class="ctx-side">
    <header class="ctx-side-head">
      <span class="ctx-side-title">上下文</span>
      <button class="ctx-side-close" title="关闭侧栏" @click="$emit('close')">×</button>
    </header>

    <div class="ctx-side-body">
      <!-- 卡片一：当前组成 -->
      <section class="ctx-card">
        <div class="ctx-card-head">
          <span class="ctx-card-title">当前组成 <span class="est-chip">估算</span></span>
          <span class="ctx-card-sub">
            {{ store.usage ? `${fmtNum(store.usage.total)} / ${fmtNum(store.usage.limit)}` : '—' }}
          </span>
        </div>

        <template v-if="store.usage">
          <div class="ctx-usage-line">
            <span class="ctx-usage-pct" :class="usageLevel">{{ usagePercent }}%</span>
            <div class="ctx-usage-track">
              <div class="ctx-usage-fill" :class="usageLevel" :style="{ width: usagePercent + '%' }"></div>
            </div>
          </div>

          <div class="stack-bar" @mouseleave="hoveredKey = ''">
            <div v-for="seg in segments" :key="seg.key" class="stack-seg"
                 :style="{ width: seg.pct + '%', background: seg.color }"
                 :class="{ dim: hoveredKey && hoveredKey !== seg.key }"
                 :title="`${seg.label} ${fmtNum(seg.value)} tok（${seg.pct}%）`"
                 @mouseenter="hoveredKey = seg.key"></div>
          </div>

          <div class="part-rows">
            <div v-for="seg in segments" :key="seg.key" class="part-row"
                 :class="{ dim: hoveredKey && hoveredKey !== seg.key }"
                 @mouseenter="hoveredKey = seg.key" @mouseleave="hoveredKey = ''">
              <span class="part-dot" :style="{ background: seg.color }"></span>
              <span class="part-label">{{ seg.label }}</span>
              <span class="part-value">{{ fmtNum(seg.value) }}</span>
              <span class="part-pct">{{ seg.pct }}%</span>
            </div>
          </div>
        </template>
        <div v-else class="ctx-empty">当前会话还没有上下文用量数据</div>
      </section>

      <!-- 卡片二：上下文时间线 -->
      <section class="ctx-card">
        <div class="ctx-card-head">
          <span class="ctx-card-title">上下文时间线</span>
          <span class="ctx-card-sub">{{ timelineSub }}</span>
        </div>

        <template v-if="hasReported">
          <div class="trend-scroll">
            <svg :width="chartWidth" :height="chartHeight" class="trend-svg">
              <!-- 每请求一根堆叠柱：新输入（下）/ 缓存命中（中）/ 输出（上） -->
              <g v-for="(bar, i) in bars" :key="i">
                <rect v-for="(seg, j) in bar.segs" :key="j"
                      :x="barX(i)" :y="seg.y" width="6" :height="seg.h"
                      :fill="seg.color" :opacity="hoverIdx !== null && hoverIdx !== i ? 0.35 : 1"
                      rx="1" />
                <rect v-if="bar.compacted" :x="barX(i)" y="0" width="6" height="3"
                      fill="#e5484d" rx="1" />
                <rect v-if="store.selectedReqSeq === bar.seq"
                      :x="barX(i) - 1.5" :y="0" width="9" :height="chartHeight"
                      fill="none" stroke="#2ec5b1" stroke-width="1.5" rx="2" />
                <!-- 命中区放大热区 -->
                <rect :x="barX(i) - 1" y="0" width="8" :height="chartHeight" fill="transparent"
                      @mouseenter="hoverIdx = i" @mouseleave="hoverIdx = null"
                      @click="store.selectRequest(bar.seq)" />
              </g>
            </svg>
          </div>

          <div class="trend-legend">
            <span><i class="dot" style="background:#2ec5b1"></i>新输入</span>
            <span><i class="dot" style="background:#8a94a6"></i>缓存命中</span>
            <span><i class="dot" style="background:#f2a35c"></i>输出</span>
            <span><i class="dot" style="background:#e5484d"></i>压缩点</span>
          </div>

          <div v-if="hoveredBar" class="trend-detail">
            <div class="trend-detail-head">
              <span>请求 #{{ hoveredBar.seq }}</span>
              <span v-if="hoveredBar.compacted" class="badge badge-danger">压缩点</span>
              <span class="trend-time">{{ fmtTimeOrDate(hoveredBar.created_at) }}</span>
            </div>
            <div class="trend-detail-line">
              输入 {{ fmtTok(hoveredBar.prompt_tokens) }}<template v-if="hoveredBar.cached_tokens">（缓存 {{ fmtTok(hoveredBar.cached_tokens) }}）</template>
              · 输出 {{ fmtTok(hoveredBar.completion_tokens) }}
              <template v-if="hoveredBar.reasoning_tokens"> · 思维链 {{ fmtTok(hoveredBar.reasoning_tokens) }}</template>
            </div>
            <div v-if="hoveredBar.model" class="trend-detail-model">{{ hoveredBar.model }}</div>
          </div>
          <div v-else class="trend-hint">悬停查看请求明细，点击选中（上下文浏览器联动）</div>
        </template>
        <div v-else class="ctx-empty">
          {{ store.timeline.length ? '端点未上报用量，无法重建时间线' : '暂无请求记录' }}
        </div>
      </section>

      <!-- 卡片三：上下文浏览器 -->
      <section class="ctx-card">
        <div class="ctx-card-head">
          <span class="ctx-card-title">上下文浏览器</span>
          <span v-if="composition" class="ctx-card-sub">查库组装</span>
        </div>

        <div v-if="selectedPoint" class="link-strip">
          <div class="link-strip-line">
            请求 #{{ selectedPoint.seq }} · 输入 {{ fmtTok(selectedPoint.prompt_tokens) }}
            <template v-if="selectedPoint.cached_tokens">（缓存 {{ fmtTok(selectedPoint.cached_tokens) }}）</template>
            · 输出 {{ fmtTok(selectedPoint.completion_tokens) }}
            <template v-if="selectedPoint.reasoning_tokens"> · 思维链 {{ fmtTok(selectedPoint.reasoning_tokens) }}</template>
          </div>
          <div class="link-strip-note">历史请求仅数值；下方明细为当前窗口</div>
        </div>

        <template v-if="composition">
          <div v-for="cat in composition.categories" :key="cat.key" class="browser-cat">
            <button class="browser-cat-head" @click="toggleCat(cat.key)">
              <span class="part-dot" :style="{ background: catColor(cat.key) }"></span>
              <span class="browser-cat-label">{{ catLabel(cat.key) }}</span>
              <span class="browser-cat-tokens">{{ catTokens(cat) }}</span>
              <span class="chev">{{ openCats[cat.key] ? '▾' : '▸' }}</span>
            </button>
            <div v-if="openCats[cat.key]" class="browser-items">
              <div v-if="!cat.items.length" class="browser-noitem">{{ catEmptyHint(cat.key) }}</div>
              <div v-for="(item, i) in cat.items" :key="i" class="browser-item">
                <button class="browser-item-head" @click="toggleItem(cat.key, i)">
                  <span class="browser-item-label">{{ itemLabel(item, cat.key, i) }}</span>
                  <span class="browser-item-tokens">{{ approxTok(item.content) }}</span>
                </button>
                <div v-if="openItems[`${cat.key}:${i}`]" class="browser-item-body">
                  <pre v-if="item.content" class="browser-pre">{{ item.content }}</pre>
                  <div v-for="(call, ci) in item.tool_calls || []" :key="ci" class="browser-call">
                    <div class="browser-call-name">⚙ {{ call.name }}</div>
                    <pre class="browser-pre">{{ call.arguments }}</pre>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>
        <div v-else class="ctx-empty">暂无组成数据</div>
      </section>
    </div>
  </aside>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useChatStore } from '../stores/chat'
import { fmtTimeOrDate } from '../utils/time'
import { usageLevelOf, usagePercentOf } from '../utils/contextUsage'

// 分类色与名：用量端点只返回三类（system_prompt/tools_schema/messages，引擎用量
// 口径，与真实请求的 system 消息/独立 tools 字段/窗口历史一一对应，组成条
// 全部展示）；上下文浏览器的类目（skills/memory 等，后端只返回可展示原文的）沿用
// 同一套色与名，其 token 数不再来自用量端点（已并入 system_prompt 估算），按条目粗估
const CATEGORY_COLORS = {
  system_prompt: '#2ec5b1',
  skills: '#5b8def',
  agents_list: '#9a7df0',
  memory: '#f2a35c',
  intent: '#e8c94e',
  tools_schema: '#ef8396',
  messages: '#8a94a6',
}

const CATEGORY_LABELS = {
  system_prompt: '系统提示词',
  skills: '技能清单',
  agents_list: '可派发清单',
  memory: '记忆块',
  intent: '意图规则',
  tools_schema: '工具定义',
  messages: '消息',
}

// 浏览器类目为空时的占位文案（后端只返回三类：技能清单/记忆块/消息）
const EMPTY_HINTS = {
  skills: '无已启用技能',
  memory: '暂无记忆块',
  messages: '暂无消息',
}

// 时间线柱段颜色：新输入/缓存命中/输出（压缩标记为红）
const TREND_COLORS = { fresh: '#2ec5b1', cached: '#8a94a6', output: '#f2a35c' }

const BAR_STEP = 8       // 柱距（柱宽 6 + 间隙 2）
const CHART_H = 90       // 图高

const store = useChatStore()
const hoveredKey = ref('')
const hoverIdx = ref(null)
const openCats = reactive({})
const openItems = reactive({})

defineEmits(['close'])

onMounted(() => {
  store.refreshTimeline()
  store.refreshComposition()
})

watch(() => store.currentId, () => {
  hoverIdx.value = null
  Object.keys(openCats).forEach((k) => delete openCats[k])
  Object.keys(openItems).forEach((k) => delete openItems[k])
  store.refreshTimeline()
  store.refreshComposition()
})

const usagePercent = computed(() => usagePercentOf(store.usage))

const usageLevel = computed(() => usageLevelOf(usagePercent.value))

// 七类按占比降序分段；占比为 0 的类不渲染空段
const segments = computed(() => {
  const parts = store.usage?.parts || {}
  const total = Object.values(parts).reduce((sum, value) => sum + (value || 0), 0)
  if (!total) return []
  return Object.entries(parts)
    .filter(([, value]) => value > 0)
    .map(([key, value]) => ({
      key,
      label: CATEGORY_LABELS[key] || key,
      color: CATEGORY_COLORS[key] || '#c8ccd6',
      value,
      pct: Math.round((value / total) * 1000) / 10,
    }))
    .sort((a, b) => b.value - a.value)
})

// 时间线：有任一请求报过用量才可绘制
const hasReported = computed(() =>
  store.timeline.some((r) => r.prompt_tokens != null || r.completion_tokens != null))

const timelineSub = computed(() => {
  if (!store.timeline.length) return '暂无请求'
  return `${store.timeline.length} 次请求`
})

// 每请求一根柱：三段（新输入/缓存/输出），高度按最大总量归一
const bars = computed(() => {
  const list = store.timeline
  if (!hasReported.value) return []
  const scaleMax = Math.max(...list.map((r) =>
    (r.prompt_tokens || 0) + (r.completion_tokens || 0)), 1)
  const usableH = CHART_H - 8
  return list.map((r) => {
    const cached = r.cached_tokens || 0
    const fresh = Math.max(0, (r.prompt_tokens || 0) - cached)
    const out = r.completion_tokens || 0
    const toH = (tokens) => Math.max(tokens > 0 ? 2 : 0, (tokens / scaleMax) * usableH)
    // 自下而上：新输入 → 缓存 → 输出
    const segs = []
    let cursor = CHART_H
    for (const [tokens, color] of [[fresh, TREND_COLORS.fresh],
      [cached, TREND_COLORS.cached], [out, TREND_COLORS.output]]) {
      if (tokens <= 0) continue
      const h = toH(tokens)
      cursor -= h
      segs.push({ y: cursor, h, color })
    }
    return { seq: r.seq, segs, ...r }
  })
})

const chartWidth = computed(() => Math.max(bars.value.length * BAR_STEP, 40))
const hoveredBar = computed(() =>
  hoverIdx.value !== null ? store.timeline[hoverIdx.value] : null)

// 浏览器卡：时间线选中的请求（有才显示联动条）
const composition = computed(() => store.composition)
const selectedPoint = computed(() =>
  store.timeline.find((r) => r.seq === store.selectedReqSeq) || null)

const ROLE_LABELS = { user: '用户', assistant: '助手', tool: '工具结果', system: '系统' }

function toggleCat(key) {
  openCats[key] = !openCats[key]
}

function toggleItem(key, index) {
  const id = `${key}:${index}`
  openItems[id] = !openItems[id]
}

function catColor(key) {
  return CATEGORY_COLORS[key] || '#c8ccd6'
}

function catLabel(key) {
  return CATEGORY_LABELS[key] || key
}

/** 类目无条目时的占位文案。 */
function catEmptyHint(key) {
  return EMPTY_HINTS[key] || '无内容'
}

/** 字符数 → token 粗估（÷4，至少 1），加 ≈ 前缀标示近似值。 */
function approxTokOf(chars) {
  return `≈${fmtTok(Math.max(1, Math.ceil(chars / 4)))}`
}

/** 类目 token 数：用量端点有对应键（system_prompt/tools_schema/messages）则直取；
 * 浏览器专属类目（skills/memory，已并入系统提示词估算）按条目字符数粗估并标 ≈。 */
function catTokens(cat) {
  const value = store.usage?.parts?.[cat.key]
  if (value != null) return fmtTok(value)
  const chars = (cat.items || []).reduce(
    (sum, item) => sum + (item.content?.length || 0), 0)
  return chars ? approxTokOf(chars) : '—'
}

/** 条目 token 近似值：Java 端点不算 token，按字符数粗估并标 ≈。 */
function approxTok(content) {
  return content ? approxTokOf(content.length) : ''
}

function itemLabel(item, key, index) {
  if (key === 'messages') {
    const role = ROLE_LABELS[item.label] || item.label
    const brief = (item.content || '').replace(/\s+/g, ' ').slice(0, 24)
    return `#${index + 1} ${role}${brief ? ` · ${brief}` : ''}`
  }
  return item.label
}

function barX(index) {
  return index * BAR_STEP + 2
}

function fmtNum(value) {
  return (value ?? 0).toLocaleString('zh-CN')
}

/** token 数缩写：千位以下原样，以上记 k（一位小数去尾零）。 */
function fmtTok(value) {
  if (value == null) return '—'
  if (value < 1000) return String(value)
  const k = value / 1000
  const text = k >= 100 ? String(Math.round(k)) : k.toFixed(1).replace(/\.0$/, '')
  return `${text}k`
}
</script>

<style scoped>
.ctx-side {
  flex: none;
  width: 320px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--line, #e6e9ed);
  background: var(--panel, #fff);
}

.ctx-side-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--line-soft, #eef0f4);
}

.ctx-side-title { font-size: 13px; font-weight: 600; color: var(--text, #2f3033); }
.ctx-side-close {
  border: none;
  background: none;
  font-size: 16px;
  line-height: 1;
  color: var(--muted, #818999);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 6px;
}
.ctx-side-close:hover { color: var(--text, #2f3033); background: var(--line-soft, #eef0f4); }

.ctx-side-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
}

.ctx-card {
  border: 1px solid var(--line-soft, #eef0f4);
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 12px;
}

.ctx-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10px;
}
.ctx-card-title { font-size: 12px; font-weight: 600; color: var(--text, #2f3033); }
.ctx-card-sub { font-size: 11px; color: var(--faint, #a6adbd); }

.ctx-usage-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.ctx-usage-pct { font-size: 12px; font-weight: 600; color: #1f9e8c; }
.ctx-usage-pct.warn { color: #b45309; }
.ctx-usage-pct.danger { color: #e5484d; }
.ctx-usage-track {
  flex: 1;
  height: 6px;
  background: #f0f1f5;
  border-radius: 3px;
  overflow: hidden;
}
.ctx-usage-fill { height: 100%; background: #2ec5b1; }
.ctx-usage-fill.warn { background: #d97706; }
.ctx-usage-fill.danger { background: #e5484d; }

.stack-bar {
  display: flex;
  height: 10px;
  border-radius: 5px;
  overflow: hidden;
  background: #f0f1f5;
  margin-bottom: 10px;
}
.stack-seg { transition: opacity 0.15s; }
.stack-seg.dim { opacity: 0.3; }

.part-rows { display: flex; flex-direction: column; }
.part-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 2px;
  border-radius: 6px;
  font-size: 11px;
  color: var(--text-soft, #4a5160);
  cursor: default;
  transition: opacity 0.15s;
}
.part-row.dim { opacity: 0.4; }
.part-dot { flex: none; width: 8px; height: 8px; border-radius: 2px; }
.part-label { flex: 1; min-width: 0; }
.part-value { font-variant-numeric: tabular-nums; color: var(--text, #2f3033); }
.part-pct { width: 44px; text-align: right; color: var(--faint, #a6adbd); font-variant-numeric: tabular-nums; }

.trend-scroll {
  overflow-x: auto;
  border-bottom: 1px solid var(--line-soft, #eef0f4);
  padding-bottom: 4px;
  margin-bottom: 8px;
}
.trend-svg { display: block; }

.trend-legend {
  display: flex;
  gap: 10px;
  font-size: 10px;
  color: var(--muted, #818999);
  margin-bottom: 8px;
}
.trend-legend .dot,
.trend-legend i {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 2px;
  margin-right: 3px;
  vertical-align: middle;
}

.trend-detail {
  background: var(--line-soft, #eef0f4);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 11px;
  color: var(--text-soft, #4a5160);
}
.trend-detail-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: var(--text, #2f3033);
  margin-bottom: 3px;
}
.trend-time { margin-left: auto; font-weight: 400; color: var(--faint, #a6adbd); }
.trend-detail-line { font-variant-numeric: tabular-nums; }
.trend-detail-model {
  margin-top: 2px;
  color: var(--faint, #a6adbd);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.trend-hint { font-size: 10px; color: var(--faint, #a6adbd); }

/* 浏览器卡 */
.link-strip {
  background: var(--brand-soft, #e8f8f5);
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 11px;
  color: var(--text-soft, #4a5160);
  margin-bottom: 8px;
}
.link-strip-line { font-variant-numeric: tabular-nums; }
.link-strip-note { margin-top: 2px; font-size: 10px; color: var(--faint, #a6adbd); }

.browser-cat { border-top: 1px solid var(--line-soft, #eef0f4); }
.browser-cat:first-of-type { border-top: none; }
.browser-cat-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 5px 2px;
  border: none;
  background: none;
  font-size: 11px;
  color: var(--text-soft, #4a5160);
  cursor: pointer;
  text-align: left;
}
.browser-cat-head:hover { color: var(--text, #2f3033); }
.browser-cat-label { flex: 1; min-width: 0; }
.est-chip {
  flex: none;
  font-size: 9px;
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 4px;
  padding: 0 4px;
}
.browser-cat-tokens {
  flex: none;
  font-variant-numeric: tabular-nums;
  color: var(--text, #2f3033);
}
.chev { flex: none; color: var(--faint, #a6adbd); }

.browser-items { padding: 0 2px 4px 14px; }
.browser-noitem { font-size: 10px; color: var(--faint, #a6adbd); padding: 2px 0; }
.browser-item-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 3px 2px;
  border: none;
  background: none;
  font-size: 10.5px;
  color: var(--muted, #818999);
  cursor: pointer;
  text-align: left;
}
.browser-item-head:hover { color: var(--text, #2f3033); }
.browser-item-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.browser-item-tokens { flex: none; font-variant-numeric: tabular-nums; }

.browser-item-body {
  border-left: 2px solid var(--line-soft, #eef0f4);
  margin: 2px 0 4px;
  padding-left: 8px;
}
.browser-pre {
  margin: 4px 0;
  padding: 6px 8px;
  background: #f7f8fa;
  border-radius: 6px;
  font-size: 10px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 220px;
  overflow-y: auto;
  color: var(--text-soft, #4a5160);
}
.browser-call { margin: 4px 0; }
.browser-call-name { font-size: 10.5px; color: var(--text, #2f3033); font-weight: 600; }

.ctx-empty { font-size: 12px; color: var(--faint, #a6adbd); padding: 8px 0; }
</style>
