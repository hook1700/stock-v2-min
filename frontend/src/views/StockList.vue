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
        />

        <el-button type="primary" style="margin-left: 12px" @click="handleSearch">
          查询
        </el-button>

        <el-button @click="handleReset">重置</el-button>

        <!-- 排序标签展示 -->
        <div v-if="sortTags.length" class="sort-tags">
          <el-tag
            v-for="(tag, index) in sortTags"
            :key="tag.field"
            closable
            size="small"
            :type="index === 0 ? '' : 'info'"
            @close="removeSort(tag.field)"
            @click="toggleSortDirection(tag.field)"
            style="cursor: pointer; margin-left: 8px"
          >
            {{ tag.label }} {{ tag.ascending ? '↑' : '↓' }}
          </el-tag>
          <el-button text type="danger" size="small" style="margin-left: 8px" @click="clearSort">
            清除排序
          </el-button>
        </div>
      </div>

      <!-- 当前日期提示 -->
      <div v-if="actualScanDate" class="date-hint">
        <el-text type="info" size="small">数据日期：{{ actualScanDate }}</el-text>
      </div>

      <!-- 未搜索时的提示 -->
      <el-empty
        v-if="!hasSearched"
        description="请选择日期后点击查询按钮"
        :image-size="120"
      >
        <template #description>
          <p style="color: #909399; font-size: 14px">请选择数据日期，点击「查询」按钮显示股票列表</p>
        </template>
      </el-empty>

      <!-- 数据表格（仅搜索后显示） -->
      <template v-if="hasSearched">
        <el-table
          :data="tableData"
          stripe
          style="width: 100%"
          border
          @sort-change="handleSortChange"
        >
          <el-table-column prop="stock_code" label="股票代码" width="110" />
          <el-table-column prop="stock_name" label="股票名称" width="120" />
          <el-table-column prop="data_date" label="数据日期" width="120" />
          <el-table-column label="最新价" width="100" align="right">
            <template #default="{ row }">
              <span v-if="row.latest_price">{{ row.latest_price.toFixed(2) }}</span>
              <span v-else class="text-muted">--</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="change_pct"
            label="涨跌幅"
            width="110"
            align="right"
            sortable="custom"
            :sort-orders="['ascending', 'descending', null]"
          >
            <template #default="{ row }">
              <span v-if="row.change_pct != null" :class="row.change_pct >= 0 ? 'price-up' : 'price-down'">
                {{ row.change_pct >= 0 ? '+' : '' }}{{ row.change_pct.toFixed(2) }}%
              </span>
              <span v-else class="text-muted">--</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="volume"
            label="成交量"
            width="120"
            align="right"
            sortable="custom"
            :sort-orders="['ascending', 'descending', null]"
          >
            <template #default="{ row }">
              <span v-if="row.volume">{{ formatVolume(row.volume) }}</span>
              <span v-else class="text-muted">--</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="turnover"
            label="换手率"
            width="110"
            align="right"
            sortable="custom"
            :sort-orders="['ascending', 'descending', null]"
          >
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

        <!-- 搜索后无数据 -->
        <el-empty v-if="hasSearched && tableData.length === 0 && !loading" description="该日期暂无数据" />
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { getStockList } from '@/api/stocks'

const loading = ref(false)
const keyword = ref('')
const scanDate = ref('')
const tableData = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const actualScanDate = ref('')
const hasSearched = ref(false)

// 组合排序状态: [{field, ascending}]
const sortList = ref([])

const FIELD_LABELS = {
  change_pct: '涨跌幅',
  volume: '成交量',
  turnover: '换手率',
}

const sortTags = computed(() =>
  sortList.value.map(s => ({
    field: s.field,
    label: FIELD_LABELS[s.field] || s.field,
    ascending: s.ascending,
  }))
)

function buildSortParam() {
  if (!sortList.value.length) return ''
  return sortList.value
    .map(s => (s.ascending ? '' : '-') + s.field)
    .join(',')
}

async function fetchData() {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
    }
    if (keyword.value) params.keyword = keyword.value
    if (scanDate.value) params.scan_date = scanDate.value
    const sortParam = buildSortParam()
    if (sortParam) params.sort_by = sortParam

    const res = await getStockList(params)
    tableData.value = res.items || []
    total.value = res.total || 0
    actualScanDate.value = res.scan_date || ''
    hasSearched.value = true
  } catch (e) {
    console.error('获取股票列表失败:', e)
  } finally {
    loading.value = false
  }
}

function handleSortChange({ prop, order }) {
  if (!prop) return
  // 移除该字段已有的排序
  const idx = sortList.value.findIndex(s => s.field === prop)
  if (idx !== -1) sortList.value.splice(idx, 1)

  if (order) {
    // 追加到排序列表末尾（支持组合排序）
    sortList.value.push({
      field: prop,
      ascending: order === 'ascending',
    })
  }

  currentPage.value = 1
  fetchData()
}

function toggleSortDirection(field) {
  const item = sortList.value.find(s => s.field === field)
  if (item) {
    item.ascending = !item.ascending
    currentPage.value = 1
    fetchData()
  }
}

function removeSort(field) {
  sortList.value = sortList.value.filter(s => s.field !== field)
  currentPage.value = 1
  fetchData()
}

function clearSort() {
  sortList.value = []
  currentPage.value = 1
  fetchData()
}

function handleSearch() {
  currentPage.value = 1
  fetchData()
}

function handleReset() {
  keyword.value = ''
  scanDate.value = ''
  sortList.value = []
  currentPage.value = 1
  tableData.value = []
  total.value = 0
  actualScanDate.value = ''
  hasSearched.value = false
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
  flex-wrap: wrap;
}

.sort-tags {
  display: flex;
  align-items: center;
  margin-left: 12px;
}

.date-hint {
  margin-bottom: 12px;
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
