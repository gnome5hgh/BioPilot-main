import { reactive } from 'vue'

/**
 * 全局确认框状态。调用 confirmDialog({...}) 返回 Promise<boolean>，由挂在 App
 * 上的 ConfirmDialog 统一渲染——替换散落各页的 window.confirm / 两步删除。
 */
export const confirmState = reactive({
  open: false,
  title: '请确认',
  message: '',
  detail: '',
  confirmText: '确认',
  cancelText: '取消',
  danger: false,
  _resolve: null,
})

let resolver = null

/**
 * 打开确认框。
 *
 * @param {object} options
 * @param {string} [options.title] 标题
 * @param {string} [options.message] 正文
 * @param {string} [options.detail] 次要说明（可选）
 * @param {string} [options.confirmText] 确认按钮文案
 * @param {boolean} [options.danger] 危险操作（红色确认按钮）
 * @returns {Promise<boolean>} 用户选择
 */
export function confirmDialog({
  title = '请确认',
  message = '',
  detail = '',
  confirmText = '确认',
  cancelText = '取消',
  danger = false,
} = {}) {
  if (resolver) resolver(false)
  confirmState.open = true
  confirmState.title = title
  confirmState.message = message
  confirmState.detail = detail
  confirmState.confirmText = confirmText
  confirmState.cancelText = cancelText
  confirmState.danger = danger
  return new Promise((resolve) => {
    resolver = (value) => {
      confirmState.open = false
      resolver = null
      resolve(value)
    }
  })
}

/** 由 ConfirmDialog 内部调用：结算当前确认框。 */
export function settleConfirm(value) {
  if (resolver) resolver(Boolean(value))
}
