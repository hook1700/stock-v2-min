<template>
  <el-card class="strategy-card" shadow="hover" @click="$emit('click')">
    <template #header>
      <div class="card-header">
        <div class="header-left">
          <span class="strategy-name">{{ strategy.strategy_name }}</span>
          <el-tag :type="statusType" size="small" class="status-tag">
            {{ statusText }}
          </el-tag>
        </div>
      </div>
    </template>

    <p class="description">{{ strategy.description }}</p>

    <div class="recommendations" v-if="strategy.recommendations.length">
      <div
        v-for="(rec, idx) in strategy.recommendations"
        :key="rec.stock_code"
        class="rec-item"
      >
        <div class="rec-left">
          <span class="rec-rank">#{{ idx + 1 }}</span>
          <div class="rec-info">
            <span class="stock-name">{{ rec.stock_name }}</span>
            <span class="stock-code">{{ rec.stock_code }}</span>
          </div>
        </div>
        <div class="rec-right">
          <div class="price-info">
            <span class="current-price">{{ rec.current_price?.toFixed(2) }}</span>
            <span class="confidence">置信度 {{ (rec.confidence_score * 100).toFixed(0) }}%</span>
          </div>
        </div>
      </div>
    </div>

    <el-empty v-else description="暂无推荐" :image-size="40" />

    <div class="card-footer" v-if="strategy.last_run_date">
      <span class="run-date">{{ strategy.last_run_date }}</span>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  strategy: {
    type: Object,
    required: true,
  },
})

defineEmits(['click'])

const statusType = computed(() => {
  if (props.strategy.last_run_status === 'SUCCESS') return 'success'
  if (props.strategy.last_run_status === 'FAILED') return 'danger'
  return 'info'
})

const statusText = computed(() => {
  if (props.strategy.last_run_status === 'SUCCESS') return '已更新'
  if (props.strategy.last_run_status === 'FAILED') return '失败'
  return '待运行'
})
</script>

<style scoped>
.strategy-card {
  cursor: pointer;
  margin-bottom: 16px;
  transition: transform 0.2s;
}

.strategy-card:hover {
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.strategy-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.description {
  font-size: 12px;
  color: #909399;
  margin-bottom: 12px;
  line-height: 1.5;
}

.recommendations {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rec-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  background: #f9fafb;
  border-radius: 6px;
}

.rec-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rec-rank {
  font-size: 12px;
  color: #409eff;
  font-weight: 700;
  width: 24px;
}

.rec-info {
  display: flex;
  flex-direction: column;
}

.stock-name {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}

.stock-code {
  font-size: 11px;
  color: #909399;
}

.rec-right {
  text-align: right;
}

.current-price {
  font-size: 14px;
  font-weight: 600;
  color: #e6a23c;
  display: block;
}

.confidence {
  font-size: 11px;
  color: #67c23a;
}

.card-footer {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
}

.run-date {
  font-size: 11px;
  color: #c0c4cc;
}
</style>
