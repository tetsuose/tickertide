import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Static client build (PRD §5: zero-backend, nightly JSON). base './' keeps the
// bundle path-relative so it serves from any subpath (Cloudflare Pages / file://).
// Output -> web/dist (gitignored). Data is loaded at runtime from public/data/.
export default defineConfig({
  plugins: [react()],
  base: './',
})
