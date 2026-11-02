/** 文件原文的鉴权读取与预览分类：预览弹层与列表下载共用同一套路径规则。 */

const TOKEN_KEY = 'biopilot_token'

/**
 * 文件原文端点（论文与数据文件各一条，均经 SpringBoot 透传到引擎）。
 *
 * @param {'paper'|'file'} kind 文件类别
 * @param {string} id 论文或数据文件 id
 * @param {boolean} download 是否作为附件下载
 * @returns {string} 带 /api 前缀的相对地址
 */
export function fileContentUrl(kind, id, download = false) {
  const base = kind === 'paper' ? 'papers' : 'files'
  return `/api/v1/${base}/${id}/content${download ? '?download=true' : ''}`
}

/**
 * 带 satoken 拉取文件 blob；失败抛 Error 由调用方转成可展示文案。
 *
 * @param {'paper'|'file'} kind 文件类别
 * @param {string} id 文件 id
 * @param {{download?: boolean}} [options] 下载选项
 * @returns {Promise<Blob>} 文件内容
 */
export async function fetchFileBlob(kind, id, { download = false } = {}) {
  const response = await fetch(fileContentUrl(kind, id, download), {
    headers: { satoken: localStorage.getItem(TOKEN_KEY) || '' },
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.blob()
}

/**
 * 用临时 object URL 触发浏览器下载，并立即释放该 URL。
 *
 * @param {Blob} blob 文件内容
 * @param {string} name 下载文件名
 */
export function triggerDownload(blob, name) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name || 'download'
  link.click()
  URL.revokeObjectURL(url)
}

/**
 * 按扩展名决定预览方式；未知类型走二进制兜底（仅提供下载）。
 *
 * @param {string} name 文件名
 * @returns {'pdf'|'image'|'markdown'|'csv'|'text'|'binary'} 预览类型
 */
export function previewKind(name) {
  const lower = (name || '').toLowerCase()
  if (lower.endsWith('.pdf')) return 'pdf'
  if (/\.(png|jpe?g|gif|webp|bmp|svg)$/.test(lower)) return 'image'
  if (/\.(md|markdown)$/.test(lower)) return 'markdown'
  if (/\.(csv|tsv)$/.test(lower)) return 'csv'
  if (/\.(txt|json|log|py|r|yaml|yml)$/.test(lower)) return 'text'
  return 'binary'
}

/**
 * CSV/TSV 预览只取前若干行若干列，避免大表撑爆 DOM。
 *
 * @param {string} text 文件文本
 * @param {string} separator 分隔符（, 或 \t）
 * @returns {string[][]} 二维单元格
 */
export function parseCsvPreview(text, separator) {
  return text.split(/\r?\n/).slice(0, 200)
    .map((line) => line.split(separator).slice(0, 20))
}
