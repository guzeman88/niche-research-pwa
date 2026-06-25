import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      // Force immediate activation — critical for mobile Safari where users can't hard-refresh
      includeAssets: ['favicon.svg', 'icon-72x72.png', 'icon-96x96.png', 'icon-128x128.png', 'icon-144x144.png', 'icon-152x152.png', 'icon-192x192.png', 'icon-384x384.png', 'icon-512x512.png'],
      injectRegister: 'auto',
      manifest: {
        name: 'Niche Research',
        short_name: 'NicheResearch',
        description: 'Multi-source Etsy niche intelligence tool',
        theme_color: '#202631',
        background_color: '#202631',
        display: 'standalone',
        orientation: 'any',
        start_url: '/?v=13',
        icons: [
          { src: 'icon-72x72.png', sizes: '72x72', type: 'image/png' },
          { src: 'icon-96x96.png', sizes: '96x96', type: 'image/png' },
          { src: 'icon-128x128.png', sizes: '128x128', type: 'image/png' },
          { src: 'icon-144x144.png', sizes: '144x144', type: 'image/png' },
          { src: 'icon-152x152.png', sizes: '152x152', type: 'image/png' },
          { src: 'icon-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-384x384.png', sizes: '384x384', type: 'image/png' },
          { src: 'icon-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icon-192x192-maskable.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
          { src: 'icon-512x512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,ico,png,svg,woff2}'],
        globIgnores: ['**/data/*.json', '**/index.html', '**/manifest.webmanifest'],
        navigateFallback: undefined,
        skipWaiting: true,
        clientsClaim: true,
        cleanupOutdatedCaches: true,
        cacheId: 'etsy-niches-v13',
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
        runtimeCaching: [],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
