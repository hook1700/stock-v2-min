import { defineStore } from 'pinia'
import { getSectorRotation } from '@/api/sectors'

export const useSectorStore = defineStore('sector', {
  state: () => ({
    rotation: {
      scan_date: null,
      opportunity_sectors: [],
      risk_sectors: [],
      neutral_sectors: [],
    },
    loading: false,
  }),

  actions: {
    async fetchSectorRotation() {
      this.loading = true
      try {
        this.rotation = await getSectorRotation()
      } catch (e) {
        console.error('获取板块轮动数据失败:', e)
      } finally {
        this.loading = false
      }
    },
  },
})
