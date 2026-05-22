<template>
  <div ref="chartRef" :style="{ width: '100%', height: height + 'px' }"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  klineData: { type: Array, default: () => [] },
  maData: { type: Object, default: () => ({}) },
  height: { type: Number, default: 400 },
})

const chartRef = ref(null)
let chart = null

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  renderChart()
}

function renderChart() {
  if (!chart || !props.klineData || !props.klineData.length) return

  const dates = props.klineData.map(item => item[0])
  const ohlc = props.klineData.map(item => [item[1], item[2], item[3], item[4]])  // open, close, low, high
  const volumes = props.klineData.map(item => item[5])

  // 计算涨跌色
  const volumeColors = props.klineData.map((item, i) => {
    if (i === 0) return item[2] >= item[1] ? '#ef5350' : '#26a69a'
    return item[2] >= props.klineData[i - 1][2] ? '#ef5350' : '#26a69a'
  })

  const series = [
    {
      name: 'K线',
      type: 'candlestick',
      data: ohlc,
      xAxisIndex: 0,
      yAxisIndex: 0,
      itemStyle: {
        color: '#ef5350',      // 阳线填充
        color0: '#26a69a',     // 阴线填充
        borderColor: '#ef5350',
        borderColor0: '#26a69a',
      },
    },
    {
      name: '成交量',
      type: 'bar',
      data: volumes.map((vol, i) => ({
        value: vol,
        itemStyle: { color: volumeColors[i] + '80' },
      })),
      xAxisIndex: 1,
      yAxisIndex: 1,
    },
  ]

  // 添加均线
  const maColors = { ma5: '#ff9800', ma10: '#2196f3', ma20: '#9c27b0', ma60: '#4caf50' }
  const maNames = { ma5: 'MA5', ma10: 'MA10', ma20: 'MA20', ma60: 'MA60' }

  for (const [key, values] of Object.entries(props.maData)) {
    if (values && values.length) {
      series.push({
        name: maNames[key] || key,
        type: 'line',
        data: values,
        smooth: true,
        lineStyle: { width: 1, color: maColors[key] || '#999' },
        symbol: 'none',
        xAxisIndex: 0,
        yAxisIndex: 0,
      })
    }
  }

  const option = {
    animation: false,
    legend: {
      data: ['K线', ...Object.values(maNames)],
      top: 0,
      textStyle: { fontSize: 11 },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: function(params) {
        const kline = params.find(p => p.seriesName === 'K线')
        if (!kline) return ''
        const [open, close, low, high] = kline.data
        const vol = params.find(p => p.seriesName === '成交量')
        return `
          <div style="font-size:12px;">
            <div><b>${kline.axisValue}</b></div>
            <div>开: ${open?.toFixed(2)} 收: ${close?.toFixed(2)}</div>
            <div>高: ${high?.toFixed(2)} 低: ${low?.toFixed(2)}</div>
            <div>量: ${vol ? (vol.value / 10000).toFixed(0) + '万' : '-'}</div>
          </div>
        `
      },
    },
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
    },
    grid: [
      { left: '8%', right: '3%', top: '10%', height: '55%' },
      { left: '8%', right: '3%', top: '72%', height: '18%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        gridIndex: 0,
        axisLabel: { show: false },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#ddd' } },
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 1,
        axisLabel: { fontSize: 10, color: '#999' },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#ddd' } },
      },
    ],
    yAxis: [
      {
        scale: true,
        gridIndex: 0,
        splitLine: { lineStyle: { color: '#f5f5f5' } },
        axisLabel: { fontSize: 10 },
      },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        splitLine: { show: false },
        axisLabel: {
          fontSize: 10,
          formatter: (val) => (val / 10000).toFixed(0) + '万',
        },
      },
    ],
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: [0, 1],
        start: 50,
        end: 100,
      },
      {
        type: 'slider',
        xAxisIndex: [0, 1],
        bottom: '2%',
        height: 20,
        start: 50,
        end: 100,
      },
    ],
    series,
  }

  chart.setOption(option, true)
}

function handleResize() {
  chart?.resize()
}

onMounted(() => {
  nextTick(initChart)
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
})

watch(() => [props.klineData, props.maData], () => {
  nextTick(renderChart)
}, { deep: true })
</script>
