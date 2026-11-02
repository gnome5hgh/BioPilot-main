/**
 * 时间展示：后端按 UTC ISO（带 +00:00）或本地无时区字符串返回，统一在展示层
 * 转成本地时间。页面里不要再出现 `slice(0, 16).replace('T', ' ')` 这类写法——
 * 它会把 UTC 当成本地时间，整站差 8 小时。
 */

/** 把后端时间值解析成 Date；无法解析时返回 null。 */
export function parseTime(value) {
  if (!value) return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  const text = String(value)
  // 纯日期（2026-11-02）按本地零点解析；带 Z / 时区的交给 Date 自己换算。
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? null : date
}

/** 完整的本地日期时间（2026-11-02 10:28）。 */
export function fmtDateTime(value) {
  const d = parseTime(value)
  if (!d) return '—'
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 只到分钟的本地时间（10:28）；跨天时补日期。 */
export function fmtTimeOrDate(value) {
  const d = parseTime(value)
  if (!d) return '—'
  const now = new Date()
  const sameDay = d.getFullYear() === now.getFullYear()
    && d.getMonth() === now.getMonth()
    && d.getDate() === now.getDate()
  if (sameDay) {
    const pad = (n) => String(n).padStart(2, '0')
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 相对时间（刚刚 / 12 分钟前 / 昨天 / 3 天前）；列表里比绝对时间更好扫。 */
export function fmtRelative(value) {
  const d = parseTime(value)
  if (!d) return '—'
  const diff = Date.now() - d.getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 172_800_000) return '昨天'
  if (diff < 604_800_000) return `${Math.floor(diff / 86_400_000)} 天前`
  return fmtDateTime(value).slice(0, 10)
}

/** 字节数展示（0 字节显示 0 B，不把 14 字节四舍五入成 0 KB）。 */
export function fmtBytes(n) {
  const size = Number(n)
  if (!size) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
