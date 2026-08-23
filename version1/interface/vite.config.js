import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    headers: {
      // Allow Firebase Google Sign-In popup to communicate back to the opener.
      "Cross-Origin-Opener-Policy": "same-origin-allow-popups",
    },
    // Serve index.html for all routes so React Router can handle them
    historyApiFallback: true,
  },
})
