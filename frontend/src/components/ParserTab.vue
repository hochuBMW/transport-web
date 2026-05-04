<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import axios from 'axios'
import { Play, Square, RefreshCw, Database } from 'lucide-vue-next'
import { API_BASE } from '../apiBase.js'

const status = ref({
  running: false,
  pid: null,
  uptime_sec: 0,
  log_file: '',
})
const logText = ref('')
const logLines = ref(200)
const useDb = ref(true)
const parserCookie = ref('')
const loading = ref(false)
const error = ref('')
let timer = null

const formatUptime = (totalSec) => {
  const sec = Number(totalSec) || 0
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const fetchStatus = async () => {
  const res = await axios.get(`${API_BASE}/parser/status`)
  status.value = res.data
}

const fetchLogs = async () => {
  const res = await axios.get(`${API_BASE}/parser/logs`, { params: { lines: logLines.value } })
  status.value = {
    running: res.data.running,
    pid: res.data.pid,
    uptime_sec: res.data.uptime_sec,
    log_file: res.data.log_file,
  }
  logText.value = res.data.log || ''
}

const refreshAll = async () => {
  try {
    error.value = ''
    await fetchLogs()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  }
}

const startParser = async () => {
  try {
    loading.value = true
    error.value = ''
    await axios.post(`${API_BASE}/parser/start`, {
      use_db: useDb.value,
      cookie: parserCookie.value.trim() ? parserCookie.value.trim() : null,
    })
    await refreshAll()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

const stopParser = async () => {
  try {
    loading.value = true
    error.value = ''
    await axios.post(`${API_BASE}/parser/stop`)
    await refreshAll()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await refreshAll()
  timer = setInterval(refreshAll, 3000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="h-full bg-gray-100 p-4 md:p-6 overflow-auto">
    <div class="max-w-6xl mx-auto space-y-4">
      <div class="bg-white rounded-xl border border-gray-200 p-4 md:p-5 shadow-sm">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="text-xl font-bold text-gray-800">Парсер IrkBus</h2>
            <p class="text-sm text-gray-500">Ручной запуск/остановка и просмотр логов в реальном времени.</p>
          </div>
          <button
            @click="refreshAll"
            class="inline-flex items-center gap-2 px-3 py-2 text-sm rounded-lg border border-gray-200 hover:bg-gray-50"
            :disabled="loading"
          >
            <RefreshCw class="w-4 h-4" /> Обновить
          </button>
        </div>

        <div class="mt-4 grid grid-cols-1 md:grid-cols-4 gap-3 text-sm">
          <div class="rounded-lg border p-3 bg-gray-50">
            <div class="text-gray-500">Статус</div>
            <div :class="status.running ? 'text-green-600' : 'text-gray-700'" class="font-semibold">
              {{ status.running ? 'Работает' : 'Остановлен' }}
            </div>
          </div>
          <div class="rounded-lg border p-3 bg-gray-50">
            <div class="text-gray-500">PID</div>
            <div class="font-semibold text-gray-800">{{ status.pid ?? '—' }}</div>
          </div>
          <div class="rounded-lg border p-3 bg-gray-50">
            <div class="text-gray-500">Uptime</div>
            <div class="font-semibold text-gray-800">{{ formatUptime(status.uptime_sec) }}</div>
          </div>
          <div class="rounded-lg border p-3 bg-gray-50">
            <div class="text-gray-500">Лог-файл</div>
            <div class="font-semibold text-gray-800 break-all text-xs">{{ status.log_file || '—' }}</div>
          </div>
        </div>

        <div class="mt-4 flex flex-wrap items-center gap-3">
          <label class="inline-flex items-center gap-2 text-sm text-gray-700 bg-blue-50 border border-blue-100 px-3 py-2 rounded-lg">
            <Database class="w-4 h-4 text-blue-600" />
            <input type="checkbox" v-model="useDb" />
            Писать в PostgreSQL/PostGIS
          </label>
          <button
            @click="startParser"
            :disabled="loading || status.running"
            class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white text-sm font-semibold"
          >
            <Play class="w-4 h-4" /> Запустить
          </button>
          <button
            @click="stopParser"
            :disabled="loading || !status.running"
            class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:bg-gray-400 text-white text-sm font-semibold"
          >
            <Square class="w-4 h-4" /> Остановить
          </button>
          <label class="inline-flex items-center gap-2 text-sm text-gray-700">
            Строк лога:
            <input
              v-model.number="logLines"
              type="number"
              min="50"
              max="2000"
              step="50"
              class="w-24 px-2 py-1 border rounded-md"
            />
          </label>
        </div>

        <div class="mt-3">
          <label class="block text-sm text-gray-700 mb-1">
            Cookie (опционально, если без нее показывает <code>buses=0</code>)
          </label>
          <textarea
            v-model="parserCookie"
            rows="3"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs font-mono"
            placeholder="PHPSESSID=...; _ga=...; _gid=..."
          />
          <p class="text-xs text-gray-500 mt-1">
            Вставьте cookie из DevTools и нажмите «Запустить». Поддерживаются форматы
            <code>PHPSESSID=...; ...</code> и <code>Cookie: PHPSESSID=...; ...</code>.
            Если парсер уже запущен, кнопка «Запустить» перезапустит его с новым cookie.
          </p>
        </div>

        <p v-if="error" class="mt-3 text-sm text-red-600">{{ error }}</p>
      </div>

      <div class="bg-white rounded-xl border border-gray-200 p-4 md:p-5 shadow-sm">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-lg font-semibold text-gray-800">Логи парсера</h3>
          <span class="text-xs text-gray-500">Автообновление: 3 сек</span>
        </div>
        <pre class="bg-gray-950 text-gray-100 rounded-lg p-4 text-xs leading-5 overflow-auto h-[60vh] whitespace-pre-wrap">{{ logText || 'Лог пока пуст' }}</pre>
      </div>
    </div>
  </div>
</template>
