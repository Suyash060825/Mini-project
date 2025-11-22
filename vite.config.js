import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // This proxy ensures that calls like axios.post('/transcribe') from the frontend
    // are correctly routed to the backend running at http://localhost:8000/transcribe
    proxy: {
      '/transcribe': 'http://localhost:8000',
      '/process_content': 'http://localhost:8000'
    }
  }
})