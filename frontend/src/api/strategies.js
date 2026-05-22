import api from './index'

/** 获取所有策略概览 */
export function getStrategies() {
  return api.get('/strategies')
}

/** 获取单个策略详情 */
export function getStrategyDetail(strategyId) {
  return api.get(`/strategies/${strategyId}`)
}

/** 获取策略历史推荐 */
export function getStrategyHistory(strategyId, page = 1, pageSize = 20) {
  return api.get(`/strategies/${strategyId}/history`, {
    params: { page, page_size: pageSize },
  })
}

/** 手动触发单个策略 */
export function runStrategy(strategyId) {
  return api.post(`/strategies/${strategyId}/run`)
}
