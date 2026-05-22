<template>
  <div class="sidebar">
    <div class="logo">
      <el-icon :size="24"><TrendCharts /></el-icon>
      <span class="logo-text">选股策略系统</span>
    </div>

    <el-menu
      :default-active="currentRoute"
      router
      background-color="#1d1e2c"
      text-color="#a3a6b4"
      active-text-color="#409eff"
    >
      <el-menu-item index="/">
        <el-icon><DataBoard /></el-icon>
        <span>策略总览</span>
      </el-menu-item>

      <el-sub-menu index="strategies">
        <template #title>
          <el-icon><Aim /></el-icon>
          <span>选股策略</span>
        </template>
        <el-menu-item index="/strategy/1">杯柄形态突破</el-menu-item>
        <el-menu-item index="/strategy/2">均线多头回踩</el-menu-item>
        <el-menu-item index="/strategy/3">底部放量回调</el-menu-item>
        <el-menu-item index="/strategy/4">高股息低波</el-menu-item>
      </el-sub-menu>

      <el-menu-item index="/sectors">
        <el-icon><PieChart /></el-icon>
        <span>板块轮动</span>
      </el-menu-item>

      <el-menu-item index="/history">
        <el-icon><Clock /></el-icon>
        <span>历史推荐</span>
      </el-menu-item>
    </el-menu>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const currentRoute = computed(() => route.path)
</script>

<style scoped>
.sidebar {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 20px;
  color: #fff;
}

.logo-text {
  font-size: 16px;
  font-weight: 600;
}

:deep(.el-menu) {
  border-right: none;
}

:deep(.el-menu-item.is-active) {
  background-color: #262838 !important;
}
</style>
