import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { title: '策略总览' },
  },
  {
    path: '/strategy/:id',
    name: 'StrategyDetail',
    component: () => import('@/views/StrategyDetail.vue'),
    meta: { title: '策略详情' },
  },
  {
    path: '/sectors',
    name: 'SectorAnalysis',
    component: () => import('@/views/SectorAnalysis.vue'),
    meta: { title: '板块轮动' },
  },
  {
    path: '/stock/:code',
    name: 'StockDetail',
    component: () => import('@/views/StockDetail.vue'),
    meta: { title: '个股详情' },
  },
  {
    path: '/history',
    name: 'History',
    component: () => import('@/views/History.vue'),
    meta: { title: '历史推荐' },
  },
  {
    path: '/stock-list',
    name: 'StockList',
    component: () => import('@/views/StockList.vue'),
    meta: { title: '股票列表' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  document.title = `${to.meta.title || '首页'} - 股票选股策略系统`
  next()
})

export default router
