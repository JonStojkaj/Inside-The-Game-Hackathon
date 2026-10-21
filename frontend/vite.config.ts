import { createReadStream, existsSync, statSync } from 'node:fs'
import { extname, join, normalize, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

const EXPORT_DIR = resolve(process.env.EXPORT_DIR ?? resolve(fileURLToPath(new URL('.', import.meta.url)), '../data/export'))
const TYPES: Record<string, string> = { '.json': 'application/json', '.mp4': 'video/mp4' }

/** Dev only: serve the backend's export folder (data/export/<id>/) at /export/<id>/. */
function serveExports(): Plugin {
  return {
    name: 'serve-exports',
    configureServer(server) {
      server.middlewares.use('/export', (req, res, next) => {
        const rel = normalize(decodeURIComponent((req.url ?? '/').split('?')[0])).replace(/^(\.\.[/\\])+/, '')
        const file = join(EXPORT_DIR, rel)
        if (!file.startsWith(EXPORT_DIR) || !existsSync(file) || !statSync(file).isFile()) return next()
        const size = statSync(file).size
        res.setHeader('Content-Type', TYPES[extname(file)] ?? 'application/octet-stream')
        res.setHeader('Accept-Ranges', 'bytes')
        const range = req.headers.range?.match(/bytes=(\d*)-(\d*)/)
        if (range) {
          // video seeking needs range requests
          const start = range[1] ? Number(range[1]) : 0
          const end = range[2] ? Number(range[2]) : size - 1
          res.statusCode = 206
          res.setHeader('Content-Range', `bytes ${start}-${end}/${size}`)
          res.setHeader('Content-Length', end - start + 1)
          createReadStream(file, { start, end }).pipe(res)
          return
        }
        res.setHeader('Content-Length', size)
        createReadStream(file).pipe(res)
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), serveExports()],
  server: {
    // backend API (FastAPI) for VITE_DATA_SOURCE=api with VITE_API_BASE unset
    proxy: { '/api': { target: process.env.API_PROXY ?? 'http://localhost:8000', ws: true } },
  },
})
