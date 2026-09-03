import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), '')
    const backendTarget = env.VITE_BACKEND_URL || 'http://127.0.0.1:8002'

    return {
        plugins: [react()],
        build: {
            chunkSizeWarningLimit: 800,
            rollupOptions: {
                output: {
                    manualChunks(id) {
                        if (!id.includes('node_modules')) {
                            return undefined
                        }
                        if (id.includes('recharts') || id.includes('d3')) {
                            return 'vendor-charts'
                        }
                        return 'vendor'
                    },
                },
            },
        },
        server: {
            proxy: {
                '/api': {
                    target: backendTarget,
                    changeOrigin: true,
                    rewrite: (path) => path.replace(/^\/api/, ''),
                },
            },
        },
    }
})
