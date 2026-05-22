<template>
  <div class="header-left">
    <h2 class="page-title">{{ route.meta.title || '策略总览' }}</h2>
  </div>

  <div class="header-right">
    <div class="status-info" v-if="strategyStore.systemStatus">
      <el-tag :type="statusTagType" size="small">
        <el-icon class="status-dot"><CircleCheck /></el-icon>
        {{ statusText }}
      </el-tag>
      <span class="last-run" v-if="strategyStore.systemStatus.last_run_time">
        上次运行: {{ formatTime(strategyStore.systemStatus.last_run_time) }}
      </span>
    </div>

    <el-button
      type="primary"
      :loading="strategyStore.running"
      @click="handleRunAll"
      size="small"
    >
      <el-icon><VideoPlay /></el-icon>
      立即执行
    </el-button>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useStrategyStore } from '@/stores/strategy'

const route = useRoute()
const strategyStore = useStrategyStore()

const statusTagType = computed(() => {
  const status = strategyStore.systemStatus?.last_run_status
  if (status === 'SUCCESS') return 'success'
  if (status === 'FAILED') return 'danger'
  if (status === 'PARTIAL') return 'warning'
  return 'info'
})

const statusText = computed(() => {
  const status = strategyStore.systemStatus?.last_run_status
  if (status === 'SUCCESS') return '正常运行'
  if (status === 'FAILED') return '执行失败'
  if (status === 'PARTIAL') return '部分成功'
  return '未运行'
})

function formatTime(timeStr) {
  if (!timeStr) return ''
  const d = new Date(timeStr)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function handleRunAll() {
  try {
    const result = await strategyStore.triggerRunAll()
    if (result.success) {
      ElMessage.success(`执行完成: ${result.message}`)
      strategyStore.fetchStrategies()
      strategyStore.fetchSystemStatus()
    } else {
      ElMessage.warning(result.message)
    }
  } catch (e) {
    ElMessage.error('执行失败')
  }
}

onMounted(() => {
  strategyStore.fetchSystemStatus()
})
</script>

<style scoped>
.header-left {
  display: flex;
  align-items: center;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.status-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  margin-right: 4px;
}

.last-run {
  font-size: 12px;
  color: #909399;
}
</style>
