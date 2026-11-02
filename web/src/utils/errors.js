/** 从 axios / fetch 异常里取一条可展示的错误文案；不要吞成静默失败。 */
export function errText(error, fallback = '操作失败，请稍后重试') {
  return error?.response?.data?.msg
    || error?.response?.data?.detail
    || error?.msg
    || error?.message
    || fallback
}
