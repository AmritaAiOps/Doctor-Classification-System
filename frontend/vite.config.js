import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/detect': 'http://127.0.0.1:8000',
      '/process': 'http://127.0.0.1:8000',
      '/download': 'http://127.0.0.1:8000',
      '/category-review': 'http://127.0.0.1:8000',
    },
  },
})
