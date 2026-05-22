<template>
  <div class="history-page" v-loading="loading">
    <el-page-header @back="$router.push('/')" title="返回" content="历史推荐" />

    <div class="content">
      <div class="filter-bar">
        <el-select v-model="selectedStrategy" placeholder="选择策略" clearable @change="fetchData">
          <el-option label="全部策略" :value="0" />
          <el-option label="杯柄形态突破" :value="1" />
          <el-option label="均线多头回踩" :value="2" />
          <el-option label="底部放量回调" :value="3" />
          <el-option label="高股息低波" :value="4" />
        </el-select>
      </div>

      <el-table :data="tableData" stripe style="width: 100%">
        <el-table-column prop="scan_date" label="日期" width="110" />
        <el-table-column prop="strategy_name" label="策略" width="130" />
        <el-table-column prop="stock_name" label="股票名称" width="100" />
        <el-table-column prop="stock_code" label="代码" width="80" />
        <el-table-column label="置信度" width="80">
          <template #default="{ row }">
            {{ (row.confidence_score * 100).toFixed(0) }}%
          </template>
        </el-table-column>
        <el-table-column label="买入价" width="90">
          <template #default="{ row }">
            {{ row.buy_price?.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column label="止损价" width="90">
          <template #default="{ row }">
            <span class="price-loss">{{ row.stop_loss_price?.toFixed(2) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="目标价" width="90">
          <template #default="{ row }">
            <span class="price-profit">{{ row.take_profit_price?.toFixed(2) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="buy_reason" label="买入理由" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="$router.push(`/stock/${row.stock_code}`)">
              K线
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="total > 0"
        class="pagination"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="currentPage"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getStrategyHistory } from '@/api/strategies'

const loading = ref(false)
const selectedStrategy = ref(0)
const tableData = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

async function fetchData() {
  loading.value = true
  try {
    const strategyId = selectedStrategy.value || 1
    const res = await getStrategyHistory(strategyId, currentPage.value, pageSize.value)
    tableData.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    console.error('获取历史数据失败:', e)
  } finally {
    loading.value = false
  }
}

function handlePageChange(page) {
  currentPage.value = page
  fetchData()
}

onMounted(fetchData)
</script>

<style scoped>
.history-page {
  max-width: 1400px;
}

.content {
  margin-top: 24px;
}

.filter-bar {
  margin-bottom: 16px;
}

.price-loss {
  color: #f56c6c;
}

.price-profit {
  color: #67c23a;
}

.pagination {
  margin-top: 16px;
  justify-content: center;
}
</style>
