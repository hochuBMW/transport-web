<script setup>
import { onMounted, ref, watch, computed } from 'vue'
import Chart from 'chart.js/auto'
import 'chartjs-adapter-date-fns'
import zoomPlugin from 'chartjs-plugin-zoom'
import { TrendingUp, MapPin, ShieldAlert, Zap, Activity } from 'lucide-vue-next'

Chart.register(zoomPlugin)

const props = defineProps(['data'])
const chartCanvas = ref(null)
let chart = null

const statsItems = computed(() => {
  if (!props.data) return []
  const s = props.data.statistics || {}
  
  // Decide color for congestion index
  const ci = props.data.congestion_index || 1
  let ciColor = 'text-green-600'
  let ciBg = 'bg-green-50'
  if (ci >= 4 && ci <= 6) { ciColor = 'text-yellow-600'; ciBg = 'bg-yellow-50' }
  else if (ci > 6) { ciColor = 'text-red-600'; ciBg = 'bg-red-50' }

  return [
    { label: 'Ср. скорость', value: (props.data.avg_speed || 0).toFixed(1) + ' км/ч', icon: TrendingUp, color: 'text-blue-600', bg: 'bg-blue-50' },
    { label: 'Индекс затора', value: `${ci} / 10`, icon: Activity, color: ciColor, bg: ciBg },
    { label: 'Зон заторов', value: props.data.congestion_zones?.length || 0, icon: ShieldAlert, color: 'text-red-600', bg: 'bg-red-50' },
    { label: 'Всего точек', value: props.data.count || 0, icon: MapPin, color: 'text-gray-600', bg: 'bg-gray-100' },
    { label: 'Медиана', value: (s.median || 0).toFixed(1) + ' км/ч', icon: Zap, color: 'text-purple-600', bg: 'bg-purple-50' },
  ]
})

const initChart = () => {
  if (!chartCanvas.value) return
  if (chart) chart.destroy()

  const ctx = chartCanvas.value.getContext('2d')
  const gradient = ctx.createLinearGradient(0, 0, 0, 400)
  gradient.addColorStop(0, 'rgba(37, 99, 235, 0.2)')
  gradient.addColorStop(1, 'rgba(37, 99, 235, 0)')

  const labels = props.data?.plot?.times?.map(t => new Date(t)) || []
  const speeds = props.data?.plot?.speeds || []

  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Скорость (км/ч)',
        data: speeds,
        borderColor: '#2563eb',
        borderWidth: 2,
        fill: true,
        backgroundColor: gradient,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        intersect: false,
        mode: 'index',
      },
      plugins: {
        legend: { display: false },
        zoom: {
          pan: { enabled: true, mode: 'x' },
          zoom: {
            wheel: { enabled: true },
            pinch: { enabled: true },
            mode: 'x',
          }
        },
        tooltip: {
          backgroundColor: 'rgba(255, 255, 255, 0.95)',
          titleColor: '#1f2937',
          titleFont: { size: 12, weight: 'bold' },
          bodyColor: '#3b82f6',
          bodyFont: { size: 14, weight: '600' },
          borderColor: '#e5e7eb',
          borderWidth: 1,
          padding: 12,
          displayColors: false,
          callbacks: {
            title: (items) => {
              const date = new Date(items[0].parsed.x)
              return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
            },
            label: (item) => {
              return `Ср. скорость: ${item.parsed.y.toFixed(1)} км/ч`
            }
          }
        }
      },
      scales: {
        x: {
          type: 'time',
          time: { 
            unit: 'minute',
            stepSize: 15,
            displayFormats: {
              minute: 'HH:mm'
            }
          },
          grid: { display: false },
          ticks: { color: '#9ca3af', font: { size: 10 } }
        },
        y: {
          beginAtZero: true,
          grid: { color: '#f3f4f6' },
          ticks: { color: '#9ca3af', font: { size: 10 } }
        }
      }
    }
  })
}

const resetZoom = () => {
  if (chart) chart.resetZoom()
}

onMounted(initChart)
watch(() => props.data, initChart, { deep: true })
</script>

<template>
  <div class="h-full flex flex-col md:flex-row gap-6 overflow-hidden">
    <!-- Left: Stats Grid -->
    <div class="md:w-64 grid grid-cols-2 md:grid-cols-1 gap-3 overflow-y-auto custom-scrollbar pr-2 flex-shrink-0">
      <div 
        v-for="item in statsItems" 
        :key="item.label"
        class="bg-gray-50 border border-gray-100 p-3 rounded-xl flex items-center gap-3 transition-all hover:shadow-md"
      >
        <div :class="['p-2 rounded-lg', item.bg]">
          <component :is="item.icon" :class="['w-4 h-4', item.color]" />
        </div>
        <div class="min-w-0">
          <div class="text-[10px] text-gray-400 font-bold uppercase tracking-tighter truncate">{{ item.label }}</div>
          <div class="text-sm font-bold text-gray-800">{{ item.value }}</div>
        </div>
      </div>
    </div>

    <!-- Right: Chart Area -->
    <div class="flex-1 flex flex-col min-w-0">
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-xs font-bold text-gray-700 flex items-center gap-2">
          Профиль скорости
          <button @click="resetZoom" class="text-[10px] text-primary-600 hover:bg-primary-50 px-2 py-0.5 rounded border border-primary-100 transition-colors">Сброс зума</button>
        </h3>
        <span class="text-[9px] text-gray-400 italic hidden sm:inline text-right">Колесико — зум, зажим — перемещение</span>
      </div>
      <div class="flex-1 min-h-0 bg-gray-50/50 rounded-xl border border-gray-100 p-2">
        <canvas ref="chartCanvas"></canvas>
      </div>
    </div>
  </div>
</template>
