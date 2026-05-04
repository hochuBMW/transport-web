/** База URL бэкенда. На сервере задайте VITE_API_BASE при сборке (например http://192.168.1.5:8000). */
const fromEnv = import.meta.env.VITE_API_BASE
export const API_BASE =
  (typeof fromEnv === 'string' && fromEnv.trim()) || 'http://127.0.0.1:8000'
