<template>
  <div class="strategy-detail" v-loading="loading">
    <el-page-header @back="$router.push('/')" :title="'返回'" :content="detail?.strategy_name" />

    <div class="content" v-if="detail">
      <el-alert :title="detail.description" type="info" :closable="false" class="desc-alert" />

      <!-- 推荐列表 -->
      <h3 class="section-title">今日推荐 ({{ detail.recommendations.length }}只)</h3>

      <el-row :gutter="16">
        <el-col
          :xs="24" :md="8"
          v-for="(rec, idx) in detail.recommendations"
          :key="rec.stock_code"
        >
          <el-card class="rec-card" shadow="hover">
            <div class="rec-header">
              <div class="rank-badge">#{{ idx + 1 }}</div>
              <div>
                <div class="stock-title">
                  {{ rec.stock_name }}
                  <span class="code">{{ rec.stock_code }}</span>
                </div>
                <el-tag type="success" size="small">
                  置信度 {{ (rec.confidence_score * 100).toFixed(0) }}%
                </el-tag>
              </div>
            </div>

            <el-divider />

            <div class="price-grid">
              <div class="price-item">
                <span class="label">当前价</span>
                <span class="value current">{{ rec.current_price?.toFixed(2) }}</span>
              </div>
              <div class="price-item">
                <span class="label">买入价</span>
                <span class="value buy">{{ rec.buy_price?.toFixed(2) }}</span>
              </div>
              <div class="price-item">
                <span class="label">止损价</span>
                <span class="value loss">{{ rec.stop_loss_price?.toFixed(2) }}</span>
              </div>
              <div class="price-item">
                <span class="label">目标价</span>
                <span class="value profit">{{ rec.take_profit_price?.toFixed(2) }}</span>
              </div>
            </div>

            <el-divider />

            <div class="reason">
              <p class="reason-title">买入理由:</p>
              <p class="reason-text">{{ rec.buy_reason }}</p>
            </div>

            <div class="sell-condition">
              <p class="reason-title">卖出条件:</p>
              <p class="reason-text">{{ rec.sell_condition }}</p>
            </div>

            <el-button
              type="primary"
              text
              class="view-chart-btn"
              @click="$router.push(`/stock/${rec.stock_code}`)"
            >
              查看K线图
            </el-button>
          </el-card>
        </el-col>
      </el-row>

      <el-empty v-if="!detail.recommendations.length" description="暂无推荐，请先执行策略" />

      <!-- 手动触发 -->
      <div class="actions">
        <el-button
          type="primary"
          :loading="running"
          @click="handleRun"
        >
          重新执行此策略
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getStrategyDetail, runStrategy } from '@/api/strategies'

const route = useRoute()
const detail = ref(null)
const loading = ref(false)
const running = ref(false)

async function fetchDetail() {
  loading.value = true
  try {
    detail.value = await getStrategyDetail(route.params.id)
  } finally {
    loading.value = false
  }
}

async function handleRun() {
  running.value = true
  try {
    const result = await runStrategy(route.params.id)
    if (result.success) {
      ElMessage.success(result.message)
      fetchDetail()
    } else {
      ElMessage.warning(result.message)
    }
  } catch (e) {
    ElMessage.error('执行失败')
  } finally {
    running.value = false
  }
}

onMounted(fetchDetail)
watch(() => route.params.id, fetchDetail)
</script>

<style scoped>
.strategy-detail {
  max-width: 1200px;
}

.content {
  margin-top: 24px;
}

.desc-alert {
  margin-bottom: 24px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: #303133;
}

.rec-card {
  margin-bottom: 16px;
}

.rec-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.rank-badge {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #409eff, #337ecc);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 14px;
}

.stock-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 4px;
}

.code {
  font-size: 12px;
  color: #909399;
  margin-left: 6px;
}

.price-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.price-item {
  display: flex;
  flex-direction: column;
}

.price-item .label {
  font-size: 12px;
  color: #909399;
}

.price-item .value {
  font-size: 16px;
  font-weight: 600;
}

.value.current { color: #303133; }
.value.buy { color: #409eff; }
.value.loss { color: #f56c6c; }
.value.profit { color: #67c23a; }

.reason, .sell-condition {
  margin-top: 8px;
}

.reason-title {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.reason-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}

.view-chart-btn {
  margin-top: 12px;
}

.actions {
  margin-top: 32px;
  text-align: center;
}
</style>
