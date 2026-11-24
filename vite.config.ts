import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import {realpathSync} from 'node:fs'
import {fileURLToPath} from 'node:url'

export default defineConfig({
  // Keep Rollup's root and resolved entry on the same drive through junctions.
  root: realpathSync(fileURLToPath(new URL('.',import.meta.url))),
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api/account': 'http://127.0.0.1:8890',
      '^/api(?:/|$)': 'http://localhost:8000',
    },
  },
})
