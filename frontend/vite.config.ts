import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Development only: the real API sits behind API Gateway + Cognito, which add the user's identity.
// Locally there is no gateway, so this dev server adds a fake identity header to proxied requests.
// This setting is not part of the production build.
const devIdentity = JSON.stringify({ authorizer: { claims: { sub: 'dev-user', email: 'dev@example.com' } } })

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/v1': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        headers: { 'x-amzn-request-context': devIdentity },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
})
