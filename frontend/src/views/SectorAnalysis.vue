<template>
  <div class="sector-analysis" v-loading="sectorStore.loading">
    <el-page-header @back="$router.push('/')" title="返回" content="板块轮动分析" />

    <div class="content" v-if="rotation.scan_date">
      <el-alert
        :title="`分析日期: ${rotation.scan_date}`"
        type="info"
        :closable="false"
        class="date-alert"
      />

      <!-- 机会板块 -->
      <h3 class="section-title success-title">
        <el-icon><TrendCharts /></el-icon>
        机会板块 ({{ rotation.opportunity_sectors.length }})
      </h3>

      <el-row :gutter="16">
        <el-col
          :xs="24" :md="12" :lg="8"
          v-for="sector in rotation.opportunity_sectors"
          :key="sector.sector_code"
        >
          <el-card class="sector-card" shadow="hover">
            <div class="sector-header">
              <span class="sector-name">{{ sector.sector_name }}</span>
              <div class="header-tags">
                <el-tag :type="maSignalType(sector.ma_signal)" size="small">
                  {{ maSignalLabel(sector.ma_signal) }}
                </el-tag>
                <el-tag type="success">机会</el-tag>
              </div>
            </div>

            <div class="metrics">
              <div class="metric">
                <span class="label">综合评分</span>
                <span class="value">{{ (sector.score * 100).toFixed(0) }}分</span>
              </div>
              <div class="metric">
                <span class="label">20日动量</span>
                <span class="value" :class="sector.momentum_20d > 0 ? 'up' : 'down'">
                  {{ sector.momentum_20d > 0 ? '+' : '' }}{{ sector.momentum_20d?.toFixed(1) }}%
                </span>
              </div>
              <div class="metric">
                <span class="label">5日动量</span>
                <span class="value" :class="sector.momentum_5d > 0 ? 'up' : 'down'">
                  {{ sector.momentum_5d > 0 ? '+' : '' }}{{ sector.momentum_5d?.toFixed(1) }}%
                </span>
              </div>
            </div>

            <p class="reasoning">{{ sector.reasoning }}</p>

            <!-- 推荐股票 -->
            <div v-if="sector.recommended_stocks.length" class="stocks-section">
              <p class="stocks-title">推荐股票:</p>
              <div
                v-for="stock in sector.recommended_stocks"
                :key="stock.stock_code"
                class="stock-item"
              >
                <div class="stock-info">
                  <span class="stock-name">{{ stock.stock_name }}</span>
                  <span class="stock-code">{{ stock.stock_code }}</span>
                  <el-tag
                    :type="stockSignalType(stock.signal_type)"
                    size="small"
                    class="stock-signal-tag"
                  >
                    {{ stockSignalLabel(stock.signal_type) }}
                  </el-tag>
                </div>
                <div class="stock-prices">
                  <span class="buy">买{{ stock.buy_price?.toFixed(2) }}</span>
                  <span class="stop">止{{ stock.stop_loss_price?.toFixed(2) }}</span>
                  <span class="target">目标{{ stock.take_profit_price?.toFixed(2) }}</span>
                </div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 风险板块 -->
      <h3 class="section-title danger-title" style="margin-top: 32px">
        <el-icon><Warning /></el-icon>
        风险板块 ({{ rotation.risk_sectors.length }})
      </h3>

      <el-row :gutter="16">
        <el-col
          :xs="24" :md="12" :lg="8"
          v-for="sector in rotation.risk_sectors"
          :key="sector.sector_code"
        >
          <el-card class="sector-card risk" shadow="hover">
            <div class="sector-header">
              <span class="sector-name">{{ sector.sector_name }}</span>
              <div class="header-tags">
                <el-tag :type="maSignalType(sector.ma_signal)" size="small">
                  {{ maSignalLabel(sector.ma_signal) }}
                </el-tag>
                <el-tag type="danger">风险</el-tag>
              </div>
            </div>
            <div class="metrics">
              <div class="metric">
                <span class="label">综合评分</span>
                <span class="value">{{ (sector.score * 100).toFixed(0) }}分</span>
              </div>
              <div class="metric">
                <span class="label">20日动量</span>
                <span class="value down">
                  {{ sector.momentum_20d > 0 ? '+' : '' }}{{ sector.momentum_20d?.toFixed(1) }}%
                </span>
              </div>
            </div>
            <p class="reasoning">{{ sector.reasoning }}</p>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <el-empty v-else description="暂无板块分析数据，请先执行策略" />
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useSectorStore } from '@/stores/sector'

const sectorStore = useSectorStore()
const rotation = computed(() => sectorStore.rotation)

// 均线信号标签
function maSignalLabel(signal) {
  const map = {
    BUY_STRONG: '🚀 强势买入',
    BUY: '📈 买入',
    WARN: '⚠️ 预警',
    SELL: '🔻 清仓',
    HOLD: '⏸ 观望',
  }
  return map[signal] || '⏸ 观望'
}

// 均线信号颜色
function maSignalType(signal) {
  const map = {
    BUY_STRONG: 'success',
    BUY: 'success',
    WARN: 'warning',
    SELL: 'danger',
    HOLD: 'info',
  }
  return map[signal] || 'info'
}

// 个股形态信号标签
function stockSignalLabel(type) {
  const map = {
    BOTH: '洗盘+放量',
    VOLUME_BREAKOUT: '放量突破',
    SECTOR_BUY: '板块推荐',
  }
  return map[type] || '板块推荐'
}

// 个股形态信号颜色
function stockSignalType(type) {
  const map = {
    BOTH: 'success',
    VOLUME_BREAKOUT: 'warning',
    SECTOR_BUY: '',
  }
  return map[type] || ''
}

onMounted(() => {
  sectorStore.fetchSectorRotation()
})
</script>

<style scoped>
.sector-analysis {
  max-width: 1400px;
}

.content {
  margin-top: 24px;
}

.date-alert {
  margin-bottom: 24px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
}

.success-title { color: #67c23a; }
.danger-title { color: #f56c6c; }

.sector-card {
  margin-bottom: 16px;
}

.sector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.header-tags {
  display: flex;
  gap: 6px;
  align-items: center;
}

.sector-name {
  font-size: 16px;
  font-weight: 600;
}

.metrics {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.metric {
  display: flex;
  flex-direction: column;
}

.metric .label {
  font-size: 11px;
  color: #909399;
}

.metric .value {
  font-size: 14px;
  font-weight: 600;
}

.value.up { color: #f56c6c; }
.value.down { color: #67c23a; }

.reasoning {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  margin-bottom: 12px;
}

.stocks-section {
  border-top: 1px solid #ebeef5;
  padding-top: 12px;
}

.stocks-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}

.stock-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px dashed #f0f0f0;
}

.stock-item:last-child {
  border-bottom: none;
}

.stock-info {
  display: flex;
  align-items: center;
  gap: 6px;
}

.stock-info .stock-name {
  font-size: 13px;
  font-weight: 500;
}

.stock-info .stock-code {
  font-size: 11px;
  color: #909399;
}

.stock-prices {
  display: flex;
  gap: 8px;
  font-size: 11px;
}

.stock-prices .buy { color: #409eff; }
.stock-prices .stop { color: #f56c6c; }
.stock-prices .target { color: #67c23a; }

.stock-signal-tag {
  margin-left: 4px;
}
</style>
