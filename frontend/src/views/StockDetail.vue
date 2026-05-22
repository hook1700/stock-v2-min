<template>
  <div class="stock-detail" v-loading="loading">
    <el-page-header @back="$router.back()" title="返回" :content="stockName" />

    <div class="content" v-if="klineData">
      <el-card class="chart-card">
        <template #header>
          <div class="chart-header">
            <span>{{ stockName }} ({{ route.params.code }}) K线图</span>
            <el-radio-group v-model="period" size="small" @change="fetchData">
              <el-radio-button :value="60">60日</el-radio-button>
              <el-radio-button :value="120">120日</el-radio-button>
              <el-radio-button :value="180">180日</el-radio-button>
            </el-radio-group>
          </div>
        </template>
        <KLineChart :kline-data="klineData" :ma-data="maData" :height="500" />
      </el-card>
    </div>

    <el-empty v-if="!loading && !klineData" description="暂无K线数据" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getStockKline } from '@/api/stocks'
import KLineChart from '@/components/charts/KLineChart.vue'

const route = useRoute()
const loading = ref(false)
const klineData = ref(null)
const maData = ref({})
const stockName = ref('')
const period = ref(120)

async function fetchData() {
  loading.value = true
  try {
    const res = await getStockKline(route.params.code, period.value)
    klineData.value = res.data
    maData.value = res.ma_data
    stockName.value = res.stock_name || route.params.code
  } catch (e) {
    console.error('获取K线数据失败:', e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.stock-detail {
  max-width: 1200px;
}

.content {
  margin-top: 24px;
}

.chart-card {
  margin-bottom: 16px;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
</style>
