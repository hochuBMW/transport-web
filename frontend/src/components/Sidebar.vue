<script setup>
import { ref, watch, inject } from 'vue'
import axios from 'axios'
import { ChevronLeft, ChevronRight, Upload, Play, Trash2, Download, Activity } from 'lucide-vue-next'

const props = defineProps(['isOpen'])
const emit = defineEmits(['toggle', 'analysis-complete'])

const API_URL = "http://127.0.0.1:8000/analyze"
const isLoading = inject('isLoading')

// Parameters
const params = ref({
  start: '',
  end: '',
  include_zero: true,
  speed_thresh: 8.0,
  eps_m: 50,
  min_pts: 4,
  routes: []
})

const rawGeoJson = ref(null)
const fileName = ref('')
const notifications = ref([])
const availableRoutes = ref([])

const addNotification = (message, type = 'info') => {
  const id = Date.now()
  notifications.value.push({ id, message, type })
  setTimeout(() => {
    notifications.value = notifications.value.filter(n => n.id !== id)
  }, 5000)
}

const handleFileUpload = async (event) => {
  const file = event.target.files[0]
  if (!file) return
  fileName.value = file.name

  try {
    const text = await file.text()
    const parsed = JSON.parse(text)
    
    if (parsed.type !== "FeatureCollection") {
      throw new Error("Ожидается GeoJSON FeatureCollection")
    }
    
    rawGeoJson.value = parsed
    
    const routeSet = new Set()
    parsed.features.forEach(f => {
      if (f.properties?.route_num) {
        routeSet.add(String(f.properties.route_num))
      }
    })
    availableRoutes.value = Array.from(routeSet).sort((a, b) => a.localeCompare(b, undefined, {numeric: true}))
    
    addNotification(`Файл загружен: ${parsed.features.length} объектов`, 'success')

    // Auto-detect time range if possible
    detectTimeRange(parsed)
  } catch (e) {
    addNotification(`Ошибка: ${e.message}`, 'error')
    rawGeoJson.value = null
  }
}

const detectTimeRange = (geojson) => {
  const times = []
  
  geojson.features.forEach(f => {
    const raw = f.properties?.time
    if (!raw) return
    
    // Support DD.MM.YYYY HH:mm:ss format seen in output.geojson
    const ddmmyyyyMatch = String(raw).match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{1,2})/)
    if (ddmmyyyyMatch) {
      const [, day, month, year, hour, minute] = ddmmyyyyMatch
      // Create date and add 8 hours
      const d = new Date(year, month - 1, day, parseInt(hour) + 8, minute)
      if (!isNaN(d.getTime())) times.push(d)
    } else {
      const d = new Date(raw)
      if (!isNaN(d.getTime())) {
        d.setHours(d.getHours() + 8) // Apply offset to ISO format as well
        times.push(d)
      }
    }
  })

  if (times.length > 0) {
    const min = new Date(Math.min(...times))
    const max = new Date(Math.max(...times))
    
    const format = (d) => {
      const pad = (n) => String(n).padStart(2, '0')
      return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
    }
    
    params.value.start = format(min)
    params.value.end = format(max)
    addNotification(`Период определен: ${min.toLocaleDateString()} - ${max.toLocaleDateString()}`, "info")
  }
}

const runAnalysis = async () => {
  if (!rawGeoJson.value) {
    addNotification("Сначала загрузите GeoJSON", "warning")
    return
  }

  isLoading.value = true
  try {
    const payload = {
      geojson: rawGeoJson.value,
      start: params.value.start.replace('T', ' '),
      end: params.value.end.replace('T', ' '),
      include_zero: params.value.include_zero,
      speed_thresh: params.value.speed_thresh,
      eps_m: params.value.eps_m,
      min_pts: params.value.min_pts,
      routes: params.value.routes.length > 0 ? params.value.routes : null
    }

    const res = await axios.post(API_URL, payload)
    emit('analysis-complete', res.data)
    addNotification("Анализ завершен успешно", "success")
  } catch (e) {
    const msg = e.response?.data?.detail || e.message
    addNotification(`Ошибка анализа: ${msg}`, "error")
  } finally {
    isLoading.value = false
  }
}

const clearData = () => {
  rawGeoJson.value = null
  fileName.value = ''
  availableRoutes.value = []
  params.value.routes = []
  emit('analysis-complete', null)
  addNotification("Данные очищены", "info")
}

const exportPdf = () => {
  window.print();
}
</script>

<template>
  <aside 
    :class="[
      'bg-white border-r border-gray-200 transition-all duration-300 flex flex-col z-50',
      isOpen ? 'w-80' : 'w-16'
    ]"
  >
    <!-- Header -->
    <div class="p-4 border-b border-gray-100 flex items-center justify-between overflow-hidden whitespace-nowrap">
      <h1 v-if="isOpen" class="font-bold text-lg text-primary-600 flex items-center gap-2">
        <Activity class="w-6 h-6" />
        Анализ транспорта
      </h1>
      <button 
        @click="emit('toggle')"
        class="p-2 hover:bg-gray-100 rounded-lg text-gray-500 transition-colors"
      >
        <ChevronLeft v-if="isOpen" />
        <ChevronRight v-else />
      </button>
    </div>

    <!-- Content -->
    <div v-show="isOpen" class="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-6">
      
      <!-- Notifications inside sidebar -->
      <TransitionGroup name="list" tag="div" class="space-y-2">
        <div 
          v-for="note in notifications" 
          :key="note.id"
          :class="[
            'p-3 rounded-lg text-sm border flex items-start gap-2 animate-in slide-in-from-top-4',
            note.type === 'success' ? 'bg-green-50 border-green-200 text-green-800' :
            note.type === 'error' ? 'bg-red-50 border-red-200 text-red-800' :
            note.type === 'warning' ? 'bg-yellow-50 border-yellow-200 text-yellow-800' : 'bg-blue-50 border-blue-200 text-blue-800'
          ]"
        >
          {{ note.message }}
        </div>
      </TransitionGroup>

      <!-- Section: Load Data -->
      <div class="space-y-3">
        <h2 class="text-xs font-semibold text-gray-400 uppercase tracking-wider">Загрузка данных</h2>
        <label class="group block border-2 border-dashed border-gray-200 hover:border-primary-400 rounded-xl p-6 transition-all cursor-pointer bg-gray-50 hover:bg-white text-center">
          <Upload class="w-8 h-8 mx-auto mb-3 text-gray-300 group-hover:text-primary-500 transition-colors" />
          <span class="block text-sm font-medium text-gray-600 group-hover:text-primary-600">
            {{ fileName || 'Выберите GeoJSON файл' }}
          </span>
          <input type="file" @change="handleFileUpload" class="hidden" accept=".geojson,.json" />
        </label>
      </div>

      <!-- Section: Analysis Parameters -->
      <div class="space-y-4 pt-4 border-t border-gray-100">
        <h2 class="text-xs font-semibold text-gray-400 uppercase tracking-wider">Параметры анализа</h2>
        
        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1">
            <label class="text-xs text-gray-500">Начало</label>
            <input 
              type="datetime-local" 
              v-model="params.start" 
              class="w-full text-xs p-2 border rounded-md focus:ring-1 focus:ring-primary-500 outline-none"
            />
          </div>
          <div class="space-y-1">
            <label class="text-xs text-gray-500">Конец</label>
            <input 
              type="datetime-local" 
              v-model="params.end" 
              class="w-full text-xs p-2 border rounded-md focus:ring-1 focus:ring-primary-500 outline-none"
            />
          </div>
        </div>

        <div v-if="availableRoutes.length > 0" class="space-y-1">
          <label class="text-xs text-gray-500">Маршруты (не выбрано = все)</label>
          <div class="h-24 overflow-y-auto border border-gray-200 rounded-md p-2 bg-gray-50 custom-scrollbar grid grid-cols-2 gap-1">
            <label v-for="r in availableRoutes" :key="r" class="flex items-center gap-2 p-1 bg-white hover:bg-primary-50 border border-gray-100 rounded cursor-pointer transition-colors">
              <input type="checkbox" :value="r" v-model="params.routes" class="w-3 h-3 text-primary-600 rounded" />
              <span class="text-xs font-semibold text-gray-700">{{ r }}</span>
            </label>
          </div>
        </div>

        <div class="space-y-3">
          <div class="flex items-center justify-between p-2 bg-gray-50 rounded-lg border border-gray-100">
            <span class="text-sm text-gray-700">Включать 0 км/ч</span>
            <input 
              type="checkbox" 
              v-model="params.include_zero"
              class="w-4 h-4 text-primary-600 rounded"
            />
          </div>

          <div class="space-y-1">
            <div class="flex justify-between">
              <label class="text-xs text-gray-500">Порог затора (км/ч)</label>
              <span class="text-xs font-medium">{{ params.speed_thresh }}</span>
            </div>
            <input type="range" min="1" max="50" step="0.5" v-model="params.speed_thresh" class="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600" />
          </div>

          <div class="space-y-1">
            <div class="flex justify-between">
              <label class="text-xs text-gray-500">Радиус кластера (м)</label>
              <span class="text-xs font-medium">{{ params.eps_m }}</span>
            </div>
            <input type="range" min="10" max="200" step="10" v-model="params.eps_m" class="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600" />
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="pt-4 space-y-2">
        <button 
          @click="runAnalysis"
          :disabled="isLoading"
          class="w-full bg-primary-600 hover:bg-primary-700 disabled:bg-gray-400 text-white font-semibold py-3 px-4 rounded-xl shadow-lg shadow-primary-200 transition-all flex items-center justify-center gap-2"
        >
          <Play v-if="!isLoading" class="w-4 h-4 fill-current" />
          <div v-else class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
          Анализировать
        </button>
        
        <div class="grid grid-cols-2 gap-2">
          <button @click="clearData" class="flex items-center justify-center gap-1 py-2 text-xs font-medium text-gray-600 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors">
            <Trash2 class="w-3.5 h-3.5" /> Очистить
          </button>
          <button @click="exportPdf" class="flex items-center justify-center gap-1 py-2 text-xs font-medium text-gray-600 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors">
            <Download class="w-3.5 h-3.5" /> Экспорт
          </button>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.list-enter-active, .list-leave-active { transition: all 0.3s ease; }
.list-enter-from { opacity: 0; transform: translateY(-10px); }
.list-leave-to { opacity: 0; transform: translateX(30px); }
</style>
