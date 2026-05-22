import { defineStore } from 'pinia'
import { getStrategies, getStrategyDetail, getStrategyHistory } from '@/api/strategies'
import { getSystemStatus, runAllStrategies } from '@/api/stocks'

export const useStrategyStore = defineStore('strategy', {
  state: () => ({
    strategies: [],
    currentDetail: null,
    history: { total: 0, items: [] },
    systemStatus: null,
    loading: false,
    running: false,
  }),

  actions: {
    async fetchStrategies() {
      this.loading = true
      try {
        this.strategies = await getStrategies()
      } catch (e) {
        console.error('获取策略数据失败:', e)
      } finally {
        this.loading = false
      }
    },

    async fetchStrategyDetail(strategyId) {
      this.loading = true
      try {
        this.currentDetail = await getStrategyDetail(strategyId)
      } catch (e) {
        console.error('获取策略详情失败:', e)
      } finally {
        this.loading = false
      }
    },

    async fetchHistory(strategyId, page = 1) {
      this.loading = true
      try {
        this.history = await getStrategyHistory(strategyId, page)
      } catch (e) {
        console.error('获取历史数据失败:', e)
      } finally {
        this.loading = false
      }
    },

    async fetchSystemStatus() {
      try {
        this.systemStatus = await getSystemStatus()
      } catch (e) {
        console.error('获取系统状态失败:', e)
      }
    },

    async triggerRunAll() {
      this.running = true
      try {
        const result = await runAllStrategies()
        return result
      } finally {
        this.running = false
      }
    },
  },
})
