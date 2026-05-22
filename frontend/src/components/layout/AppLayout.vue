<template>
  <el-container class="app-layout">
    <el-aside width="220px" class="app-sidebar">
      <AppSidebar />
    </el-aside>
    <el-container>
      <el-header class="app-header">
        <AppHeader />
      </el-header>
      <el-main class="app-main">
        <slot />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import AppSidebar from './AppSidebar.vue'
import AppHeader from './AppHeader.vue'
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
}

.app-sidebar {
  background: #1d1e2c;
  border-right: 1px solid #e4e7ed;
}

.app-header {
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 60px;
}

.app-main {
  background: #f5f7fa;
  padding: 24px;
  min-height: calc(100vh - 60px);
}
</style>
