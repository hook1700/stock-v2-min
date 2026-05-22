/** 策略名称和颜色配置 */
export const STRATEGY_CONFIG = {
  1: { name: '杯柄形态突破', color: '#409eff', icon: 'TrendCharts' },
  2: { name: '均线多头回踩', color: '#67c23a', icon: 'DataLine' },
  3: { name: '底部放量回调', color: '#e6a23c', icon: 'Lightning' },
  4: { name: '高股息低波', color: '#909399', icon: 'Coin' },
}

/** 信号类型 */
export const SIGNAL_TYPES = {
  BUY: { label: '买入', color: '#f56c6c', type: 'danger' },
  SELL: { label: '卖出', color: '#67c23a', type: 'success' },
  HOLD: { label: '持有', color: '#e6a23c', type: 'warning' },
}

/** 板块信号 */
export const SECTOR_SIGNALS = {
  OPPORTUNITY: { label: '机会', color: '#67c23a', type: 'success' },
  RISK: { label: '风险', color: '#f56c6c', type: 'danger' },
  NEUTRAL: { label: '中性', color: '#909399', type: 'info' },
}
