/**
 * 上下文用量的展示口径：百分比与水位档位，胶囊（ChatView）与侧栏组成卡
 * （ContextSidebar）共用同一份，避免两处公式漂移。
 */

/** 用量占窗口上限的百分比（保留 1 位小数，封顶 100）；无数据时返回 0。 */
export function usagePercentOf(usage) {
  if (!usage || !usage.limit) return 0
  return Math.min(100, Math.round((usage.total / usage.limit) * 1000) / 10)
}

/** 水位档位：>80% 危险、>50% 警告，其余正常。 */
export function usageLevelOf(percent) {
  return percent > 80 ? 'danger' : percent > 50 ? 'warn' : 'ok'
}
