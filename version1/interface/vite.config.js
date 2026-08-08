import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    headers: {
      // Allow Firebase Google Sign-In popup to communicate back to the opener.
      // "same-origin" (Vite default) blocks window.closed checks from cross-origin popups.
      "Cross-Origin-Opener-Policy": "same-origin-allow-popups",
    },
  },
})
