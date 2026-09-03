import { useEffect, useMemo, useRef, useState } from 'react'
import { NavLink } from 'react-router-dom'
import {
    Activity,
    Bot,
    GitCompare,
    LayoutDashboard,
    LogOut,
    Moon,
    Settings,
    Sun,
    TrendingUp,
} from 'lucide-react'
import IconButton from './IconButton'
import { cn } from '../lib/cn'

function getInitial(email = '') {
    const trimmed = String(email || '').trim()
    if (!trimmed) return 'U'
    return trimmed[0].toUpperCase()
}

function TabLink({ to, icon: Icon, children }) {
    return (
        <NavLink
            to={to}
            className={({ isActive }) => cn(
                'inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                isActive ? 'bg-white/[0.08] text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.10)]' : 'text-slate-300 hover:bg-white/[0.06] hover:text-white',
            )}
            end
        >
            <Icon size={16} className="opacity-90" />
            <span>{children}</span>
        </NavLink>
    )
}

export default function TopNav({ user, theme, onToggleTheme, onLogout }) {
    const [menuOpen, setMenuOpen] = useState(false)
    const menuRef = useRef(null)

    const initial = useMemo(() => getInitial(user?.email), [user?.email])
    const isAdmin = useMemo(() => String(user?.role || '').trim().toLowerCase() === 'admin', [user?.role])

    useEffect(() => {
        const handler = (event) => {
            if (!menuRef.current) return
            if (menuRef.current.contains(event.target)) return
            setMenuOpen(false)
        }
        document.addEventListener('mousedown', handler)
        return () => document.removeEventListener('mousedown', handler)
    }, [])

    return (
        <header className="sticky top-0 z-40 border-b border-white/5 bg-black/40 backdrop-blur">
            <div className="mx-auto flex w-full max-w-6xl items-center gap-4 px-4 py-4">
                <div className="flex items-center gap-3">
                    <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-violet-500 via-fuchsia-500 to-indigo-500 shadow-[0_18px_50px_rgba(168,85,247,0.25)]">
                        <TrendingUp size={18} className="text-white" />
                    </div>
                    <div className="leading-tight">
                        <p className="text-sm font-semibold tracking-tight text-white">
                            TrendForecast<span className="text-slate-300">.ai</span>
                        </p>
                    </div>
                </div>

                <nav className="hidden flex-1 justify-center md:flex">
                    <div className="flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] p-1">
                        <TabLink to="/dashboard" icon={LayoutDashboard}>Dashboard</TabLink>
                        <TabLink to="/comparison" icon={GitCompare}>Comparison</TabLink>
                        {isAdmin ? <TabLink to="/analytics" icon={Activity}>Analytics</TabLink> : null}
                        <TabLink to="/chat" icon={Bot}>AI Chatbot</TabLink>
                        <TabLink to="/settings" icon={Settings}>Settings</TabLink>
                    </div>
                </nav>

                <div className="ml-auto flex items-center gap-2" ref={menuRef}>
                    <IconButton
                        label="Toggle theme"
                        onClick={onToggleTheme}
                    >
                        {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
                    </IconButton>

                    <div className="relative">
                        <button
                            type="button"
                            onClick={() => setMenuOpen((v) => !v)}
                            aria-label="Account menu"
                            className={cn(
                                'grid h-10 w-10 place-items-center rounded-full border border-white/10',
                                'bg-gradient-to-br from-white/[0.08] to-white/[0.02] text-sm font-semibold text-white',
                                'shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur transition hover:bg-white/[0.06]',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                            )}
                        >
                            {initial}
                        </button>

                        {menuOpen ? (
                            <div className="absolute right-0 mt-2 w-56 overflow-hidden rounded-2xl border border-white/10 bg-[#0b0d14]/90 shadow-[0_20px_60px_rgba(0,0,0,0.65)] backdrop-blur">
                                <div className="px-4 py-3">
                                    <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Signed in as</p>
                                    <p className="mt-1 truncate text-sm font-medium text-white">{user?.email || 'user'}</p>
                                </div>
                                <div className="border-t border-white/10 p-2">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setMenuOpen(false)
                                            onLogout?.()
                                        }}
                                        className={cn(
                                            'flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium',
                                            'text-slate-200 hover:bg-white/[0.06] hover:text-white',
                                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                        )}
                                    >
                                        <LogOut size={16} className="opacity-90" />
                                        Logout
                                    </button>
                                </div>
                            </div>
                        ) : null}
                    </div>
                </div>
            </div>
        </header>
    )
}

