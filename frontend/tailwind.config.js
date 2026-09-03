/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    darkMode: 'class', // Enable class-based dark mode
    theme: {
        extend: {
            colors: {
                brand: {
                    50: '#eff6ff',
                    100: '#dbeafe',
                    200: '#bfdbfe',
                    300: '#93c5fd',
                    400: '#60a5fa',
                    500: '#3b82f6',
                    600: '#2563eb',
                    700: '#1d4ed8',
                    800: '#1e40af',
                    900: '#1e3a8a',
                    950: '#172554',
                },
                dark: {
                    bg: '#020617',
                    surface: '#0f172a',
                    card: '#111827',
                    cardHover: '#1f2937',
                    border: '#334155',
                },
                tf: {
                    bg: 'rgb(var(--tf-bg) / <alpha-value>)',
                    fg: 'rgb(var(--tf-fg) / <alpha-value>)',
                    muted: 'rgb(var(--tf-muted) / <alpha-value>)',
                },
                success: '#059669',
                warning: '#d97706',
                error: '#dc2626',
            },
            fontFamily: {
                sans: ['"Space Grotesk"', '"Manrope"', 'ui-sans-serif', 'sans-serif'],
            },
            boxShadow: {
                'glow': '0 0 20px -5px rgba(37, 99, 235, 0.35)',
                'glass': '0 8px 32px 0 rgba(31, 38, 135, 0.37)'
            },
            keyframes: {
                fadeIn: {
                    '0%': { opacity: '0' },
                    '100%': { opacity: '1' },
                }
            },
            animation: {
                'fade-in': 'fadeIn 0.5s ease-out',
            }
        },
    },
    plugins: [],
}
