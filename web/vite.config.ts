import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// `npm run dev` proxies the API to a running server (compose publishes 8086).
export default defineConfig({
  plugins: [react()],
  build: {
    // The server's CSP has no font-src data:, so KaTeX fonts must stay files.
    assetsInlineLimit: (file) => (/\.(woff2?|ttf)$/.test(file) ? false : undefined),
  },
  server: {
    host: '0.0.0.0',
    proxy: { '/api': process.env.API_URL ?? 'http://127.0.0.1:8086' },
  },
})
