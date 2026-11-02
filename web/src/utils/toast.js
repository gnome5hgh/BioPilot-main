import { reactive } from 'vue'

/** 全局提示队列：任何页面 toast('...') 即可，不依赖组件上下文。 */
export const toastState = reactive({ items: [] })

let seq = 0

/**
 * 弹一条轻提示。
 *
 * @param {string} message 文案
 * @param {'info'|'success'|'error'} type 类型（错误用红色）
 * @param {number} timeout 自动消失毫秒数
 */
export function toast(message, type = 'info', timeout = 3200) {
  if (!message) return
  const id = ++seq
  toastState.items.push({ id, message, type })
  window.setTimeout(() => {
    const index = toastState.items.findIndex((item) => item.id === id)
    if (index >= 0) toastState.items.splice(index, 1)
  }, timeout)
}
