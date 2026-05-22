/** 格式化工具函数 */

/** 格式化百分比 */
export function formatPercent(value, decimals = 2) {
  if (value === null || value === undefined) return '-'
  return (value * 100).toFixed(decimals) + '%'
}

/** 格式化数字（保留小数位） */
export function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined) return '-'
  return Number(value).toFixed(decimals)
}

/** 格式化大数字（万/亿） */
export function formatLargeNumber(value) {
  if (!value) return '-'
  if (value >= 1e8) return (value / 1e8).toFixed(2) + '亿'
  if (value >= 1e4) return (value / 1e4).toFixed(0) + '万'
  return value.toFixed(0)
}

/** 格式化日期 */
export function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 格式化时间 */
export function formatDateTime(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return `${formatDate(dateStr)} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
