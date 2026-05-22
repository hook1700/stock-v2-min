import api from './index'

/** 获取股票K线数据 */
export function getStockKline(code, days = 180) {
  return api.get(`/stocks/${code}/kline`, { params: { days } })
}

/** 获取股票基本信息 */
export function getStockInfo(code) {
  return api.get(`/stocks/${code}/info`)
}

/** 获取系统状态 */
export function getSystemStatus() {
  return api.get('/system/status')
}

/** 手动触发全部策略 */
export function runAllStrategies() {
  return api.post('/system/run-all')
}
