import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// In development the UI runs on :5173 and proxies the API (`fixel serve`, default :8765).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true } } },
})
