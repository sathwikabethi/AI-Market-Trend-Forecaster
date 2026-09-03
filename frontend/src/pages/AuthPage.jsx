import { useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { cn } from '../lib/cn'
import {
    loginUser,
    registerUser,
} from '../lib/api'

function ModeButton({ active, children, ...props }) {
    return (
        <button
            type="button"
            className={cn(
                'flex-1 rounded-xl px-4 py-2 text-sm font-semibold transition',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                active
                    ? 'bg-white/[0.10] text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.10)]'
                    : 'text-slate-300 hover:bg-white/[0.06] hover:text-white',
            )}
            {...props}
        >
            {children}
        </button>
    )
}

export default function AuthPage({ onAuth }) {
    const navigate = useNavigate()
    const location = useLocation()

    const [mode, setMode] = useState('login')
    const [name, setName] = useState('')
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [mfaCode, setMfaCode] = useState('')
    const [mfaRequired, setMfaRequired] = useState(false)
    const [submitting, setSubmitting] = useState(false)

    const fromPath = useMemo(() => {
        const raw = location.state?.from?.pathname
        if (typeof raw === 'string' && raw.trim()) return raw
        return '/dashboard'
    }, [location.state?.from?.pathname])

    const switchMode = (nextMode) => {
        setMode(nextMode)
        setMfaRequired(false)
        setMfaCode('')
    }

    const submit = async (event) => {
        event.preventDefault()
        if (submitting) return

        setSubmitting(true)
        try {
            const payload = mode === 'register'
                ? await registerUser({ name, email, password })
                : await loginUser({ email, password, mfa_code: mfaCode })

            onAuth?.(payload.user)
            toast.success(mode === 'register' ? 'Account created.' : 'Welcome back.')
            navigate(fromPath, { replace: true })
        } catch (err) {
            const message = err?.response?.data?.message || err?.response?.data?.detail || 'Authentication failed.'
            if (mode === 'login' && typeof message === 'string' && message.toLowerCase().includes('mfa code')) {
                setMfaRequired(true)
            }
            toast.error(message)
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <div className="relative min-h-screen overflow-hidden bg-tf-bg text-tf-fg">
            <div
                className="pointer-events-none absolute inset-0 opacity-80"
                style={{
                    background:
                        'radial-gradient(900px circle at 20% 10%, rgba(168,85,247,0.18), transparent 55%), radial-gradient(900px circle at 75% 20%, rgba(34,211,238,0.14), transparent 50%)',
                }}
            />

            <main className="relative mx-auto flex min-h-screen w-full max-w-6xl items-center justify-center px-4 py-12">
                <section className="w-full max-w-md rounded-3xl border border-white/10 bg-white/[0.04] p-7 shadow-[0_20px_60px_rgba(0,0,0,0.55)] backdrop-blur">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
                        TrendForecast.ai
                    </p>
                    <h1 className="mt-3 text-2xl font-semibold tracking-tight text-white">
                        {mode === 'register' ? 'Create your account' : 'Sign in to continue'}
                    </h1>
                    <p className="mt-2 text-sm text-slate-400">
                        Live sentiment tracking, comparisons, and AI insights in one workspace.
                    </p>

                    <div className="mt-6 flex gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-2">
                        <ModeButton active={mode === 'login'} onClick={() => switchMode('login')}>
                            Login
                        </ModeButton>
                        <ModeButton active={mode === 'register'} onClick={() => switchMode('register')}>
                            Register
                        </ModeButton>
                    </div>

                    <form onSubmit={submit} className="mt-6 space-y-3">
                        {mode === 'register' ? (
                            <input
                                className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none transition focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-400/30"
                                placeholder="Full name"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                required
                                minLength={2}
                            />
                        ) : null}
                        <input
                            className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none transition focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-400/30"
                            type="email"
                            placeholder="Email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            autoComplete="email"
                        />
                        <input
                            className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none transition focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-400/30"
                            type="password"
                            placeholder="Password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            minLength={mode === 'register' ? 10 : 6}
                            autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                        />

                        {mode === 'login' && mfaRequired ? (
                            <input
                                className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none transition focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-400/30"
                                placeholder="MFA code"
                                value={mfaCode}
                                onChange={(e) => setMfaCode(e.target.value)}
                                required
                                minLength={6}
                                maxLength={16}
                                autoComplete="one-time-code"
                            />
                        ) : null}

                        <button
                            className={cn(
                                'mt-2 inline-flex w-full items-center justify-center rounded-2xl px-4 py-3 text-sm font-semibold transition',
                                'bg-gradient-to-r from-cyan-400 to-sky-500 text-slate-950 shadow-[0_18px_50px_rgba(34,211,238,0.18)]',
                                'hover:from-cyan-300 hover:to-sky-400',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                'disabled:cursor-not-allowed disabled:opacity-70',
                            )}
                            type="submit"
                            disabled={submitting}
                        >
                            {submitting ? 'Please wait...' : mode === 'register' ? 'Create account' : 'Sign in'}
                        </button>
                    </form>
                </section>
            </main>
        </div>
    )
}
