import { readdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import type { Plugin } from 'vite'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// pdf.js 6 decodes CCITT/JBIG2, JPEG 2000 and ICC colour with wasm modules it
// fetches by name from `wasmUrl` (pdfFind.ts), so they ship unhashed.
const PDFJS_WASM_DIR = fileURLToPath(new URL('./node_modules/pdfjs-dist/wasm/', import.meta.url))
const PDFJS_WASM_PATH = 'assets/pdfjs-wasm/'

function pdfjsWasm(): Plugin {
  const files = () => readdirSync(PDFJS_WASM_DIR).filter((f) => /^(jbig2|openjpeg|qcms).*\.(wasm|js)$/.test(f))
  return {
    name: 'pdfjs-wasm',
    configureServer(server) {
      server.middlewares.use(`/${PDFJS_WASM_PATH}`, (req, res, next) => {
        const name = (req.url ?? '').split('?')[0].replace(/^\//, '')
        if (!files().includes(name)) return next()
        res.setHeader('Content-Type', name.endsWith('.wasm') ? 'application/wasm' : 'text/javascript')
        res.end(readFileSync(PDFJS_WASM_DIR + name))
      })
    },
    generateBundle() {
      for (const name of files()) {
        this.emitFile({ type: 'asset', fileName: PDFJS_WASM_PATH + name, source: readFileSync(PDFJS_WASM_DIR + name) })
      }
    },
  }
}

// `npm run dev` proxies the API to a running server (compose publishes 8086).
export default defineConfig({
  plugins: [react(), pdfjsWasm()],
  build: {
    // The server's CSP has no font-src data:, so KaTeX fonts must stay files.
    assetsInlineLimit: (file) => (/\.(woff2?|ttf)$/.test(file) ? false : undefined),
  },
  server: {
    host: '0.0.0.0',
    proxy: { '/api': process.env.API_URL ?? 'http://127.0.0.1:8086' },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test/setup.ts'],
    coverage: { provider: 'v8', include: ['src/**/*.{ts,tsx}'], reporter: ['text-summary', 'text'] },
  },
})
