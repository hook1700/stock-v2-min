<template>
  <div class="dashboard">
    <!-- 策略卡片区 -->
    <div class="section-title">
      <h3>选股策略推荐</h3>
      <span class="subtitle" v-if="strategies.length">每个策略推荐最有机会的3只股票</span>
    </div>

    <el-row :gutter="16" v-loading="strategyStore.loading">
      <el-col :xs="24" :sm="12" :lg="6" v-for="strategy in strategies" :key="strategy.strategy_id">
        <StrategyCard :strategy="strategy" @click="goToStrategy(strategy.strategy_id)" />
      </el-col>
    </el-row>

    <!-- 板块轮动快览 -->
    <div class="section-title" style="margin-top: 32px">
      <h3>板块轮动分析</h3>
      <el-button text type="primary" @click="$router.push('/sectors')">查看详情</el-button>
    </div>

    <el-row :gutter="16" v-loading="sectorStore.loading">
      <el-col :xs="24" :md="12">
        <el-card class="sector-card opportunity">
          <template #header>
            <div class="card-header">
              <el-icon color="#67c23a"><TrendCharts /></el-icon>
              <span>机会板块</span>
            </div>
          </template>
          <div v-if="sectorStore.rotation.opportunity_sectors.length">
            <div
              v-for="sector in sectorStore.rotation.opportunity_sectors.slice(0, 5)"
              :key="sector.sector_code"
              class="sector-item"
            >
              <span class="sector-name">{{ sector.sector_name }}</span>
              <el-tag type="success" size="small">
                {{ sector.momentum_20d > 0 ? '+' : '' }}{{ sector.momentum_20d?.toFixed(1) }}%
              </el-tag>
            </div>
          </div>
          <el-empty v-else description="暂无数据" :image-size="60" />
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12">
        <el-card class="sector-card risk">
          <template #header>
            <div class="card-header">
              <el-icon color="#f56c6c"><Warning /></el-icon>
              <span>风险板块</span>
            </div>
          </template>
          <div v-if="sectorStore.rotation.risk_sectors.length">
            <div
              v-for="sector in sectorStore.rotation.risk_sectors.slice(0, 5)"
              :key="sector.sector_code"
              class="sector-item"
            >
              <span class="sector-name">{{ sector.sector_name }}</span>
              <el-tag type="danger" size="small">
                {{ sector.momentum_20d > 0 ? '+' : '' }}{{ sector.momentum_20d?.toFixed(1) }}%
              </el-tag>
            </div>
          </div>
          <el-empty v-else description="暂无数据" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useStrategyStore } from '@/stores/strategy'
import { useSectorStore } from '@/stores/sector'
import StrategyCard from '@/components/strategy/StrategyCard.vue'

const router = useRouter()
const strategyStore = useStrategyStore()
const sectorStore = useSectorStore()

const strategies = computed(() => strategyStore.strategies)

function goToStrategy(id) {
  router.push(`/strategy/${id}`)
}

onMounted(() => {
  strategyStore.fetchStrategies()
  sectorStore.fetchSectorRotation()
})
</script>

<style scoped>
.dashboard {
  max-width: 1400px;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.section-title h3 {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.subtitle {
  font-size: 13px;
  color: #909399;
  margin-left: 12px;
}

.sector-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.sector-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.sector-item:last-child {
  border-bottom: none;
}

.sector-name {
  font-size: 14px;
  color: #303133;
}
</style>
