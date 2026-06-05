/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Static client build (PRD §5: zero-backend, nightly JSON). base './' keeps the
// bundle path-relative so it serves from any subpath (Cloudflare Pages / file://).
// Output -> web/dist (gitignored). Data is loaded at runtime from public/data/.
// `test` runs the C9 parity unit test (composite.test.ts) under vitest.
export default defineConfig({
  plugins: [react()],
  base: './',
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
