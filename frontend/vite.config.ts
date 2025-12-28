import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/npl': {
        target: 'http://localhost:12000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
