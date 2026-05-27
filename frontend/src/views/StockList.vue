<template>
  <div class="stock-list-page" v-loading="loading">
    <el-page-header @back="$router.push('/')" title="返回" content="股票列表" />

    <div class="content">
      <!-- 过滤栏 -->
      <div class="filter-bar">
        <el-input
          v-model="keyword"
          placeholder="输入股票代码或名称搜索"
          clearable
          style="width: 240px"
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <el-date-picker
          v-model="scanDate"
          type="date"
          placeholder="选择数据日期"
          value-format="YYYY-MM-DD"
          clearable
          style="width: 180px; margin-left: 12px"
          @change="handleSearch"
        />

        <el-button type="primary" style="margin-left: 12px" @click="handleSearch">
          查询
        </el-button>

        <el-button @click="handleReset">重置</el-button>
      </div>

      <!-- 数据表格 -->
      <el-table :data="tableData" stripe style="width: 100%" border>
        <el-table-column prop="stock_code" label="股票代码" width="110" />
        <el-table-column prop="stock_name" label="股票名称" width="120" />
        <el-table-column prop="data_date" label="数据日期" width="120" />
        <el-table-column label="最新价" width="100" align="right">
          <template #default="{ row }">
            <span v-if="row.latest_price">{{ row.latest_price.toFixed(2) }}</span>
            <span v-else class="text-muted">--</span>
          </template>
        </el-table-column>
        <el-table-column label="涨跌幅" width="100" align="right">
          <template #default="{ row }">
            <span v-if="row.change_pct != null" :class="row.change_pct >= 0 ? 'price-up' : 'price-down'">
              {{ row.change_pct >= 0 ? '+' : '' }}{{ row.change_pct.toFixed(2) }}%
            </span>
            <span v-else class="text-muted">--</span>
          </template>
        </el-table-column>
        <el-table-column label="成交量" width="120" align="right">
          <template #default="{ row }">
            <span v-if="row.volume">{{ formatVolume(row.volume) }}</span>
            <span v-else class="text-muted">--</span>
          </template>
        </el-table-column>
        <el-table-column label="换手率" width="100" align="right">
          <template #default="{ row }">
            <span v-if="row.turnover != null">{{ row.turnover.toFixed(2) }}%</span>
            <span v-else class="text-muted">--</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="$router.push(`/stock/${row.stock_code}`)">
              K线
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <el-pagination
        v-if="total > 0"
        class="pagination"
        layout="total, sizes, prev, pager, next, jumper"
        :total="total"
        :page-size="pageSize"
        :page-sizes="[20, 50, 100]"
        :current-page="currentPage"
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { getStockList } from '@/api/stocks'

const loading = ref(false)
const keyword = ref('')
const scanDate = ref('')
const tableData = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

async function fetchData() {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
    }
    if (keyword.value) params.keyword = keyword.value
    if (scanDate.value) params.scan_date = scanDate.value

    const res = await getStockList(params)
    tableData.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    console.error('获取股票列表失败:', e)
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  currentPage.value = 1
  fetchData()
}

function handleReset() {
  keyword.value = ''
  scanDate.value = ''
  currentPage.value = 1
  fetchData()
}

function handlePageChange(page) {
  currentPage.value = page
  fetchData()
}

function handleSizeChange(size) {
  pageSize.value = size
  currentPage.value = 1
  fetchData()
}

function formatVolume(vol) {
  if (vol >= 1e8) return (vol / 1e8).toFixed(2) + '亿'
  if (vol >= 1e4) return (vol / 1e4).toFixed(0) + '万'
  return vol.toString()
}

onMounted(fetchData)
</script>

<style scoped>
.stock-list-page {
  max-width: 1400px;
}

.content {
  margin-top: 24px;
}

.filter-bar {
  margin-bottom: 16px;
  display: flex;
  align-items: center;
}

.price-up {
  color: #f56c6c;
}

.price-down {
  color: #67c23a;
}

.text-muted {
  color: #c0c4cc;
}

.pagination {
  margin-top: 16px;
  justify-content: center;
}
</style>
