import {
    MessageCircle,
    MoreHorizontal,
    Newspaper,
    RefreshCcw,
    Star,
    Twitter,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { cn } from '../lib/cn'

const SOURCE_ICON = {
    reddit: MessageCircle,
    twitter: Twitter,
    reviews: Star,
    news: Newspaper,
}

const TONE_CLASS = {
    warm: 'text-orange-300',
    cool: 'text-sky-300',
    gold: 'text-amber-300',
    slate: 'text-slate-300',
}

function HeaderAction({ variant, spinning }) {
    if (variant === 'regions') {
        return (
            <MoreHorizontal size={16} className="text-slate-400" />
        )
    }
    if (variant === 'sources') {
        return (
            <RefreshCcw size={16} className={cn('text-slate-400', spinning && 'animate-spin')} />
        )
    }
    return null
}

export default function ProgressListCard({
    title,
    variant,
    items,
    onAction,
    actionBusy = false,
    actionLabel,
    menuActions,
    onItemClick,
}) {
    const rows = Array.isArray(items) ? items : []
    const actions = Array.isArray(menuActions) ? menuActions.filter(Boolean) : []

    const [menuOpen, setMenuOpen] = useState(false)
    const menuRef = useRef(null)
    const buttonRef = useRef(null)

    useEffect(() => {
        if (variant !== 'regions' || !menuOpen) return undefined

        const handler = (event) => {
            const target = event.target
            if (buttonRef.current && buttonRef.current.contains(target)) return
            if (menuRef.current && menuRef.current.contains(target)) return
            setMenuOpen(false)
        }

        document.addEventListener('mousedown', handler)
        return () => document.removeEventListener('mousedown', handler)
    }, [menuOpen, variant])

    useEffect(() => {
        if (variant !== 'regions' || !menuOpen) return undefined
        const handler = (event) => {
            if (event.key === 'Escape') setMenuOpen(false)
        }
        document.addEventListener('keydown', handler)
        return () => document.removeEventListener('keydown', handler)
    }, [menuOpen, variant])

    return (
        <section className="rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-white/[0.03] p-5 shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur">
            <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-white">{title}</h3>
                <div className="relative">
                    <button
                        ref={buttonRef}
                        type="button"
                        onClick={() => {
                            if (variant === 'regions' && actions.length) {
                                setMenuOpen((v) => !v)
                                return
                            }
                            onAction?.()
                        }}
                        disabled={actionBusy}
                        className={cn(
                            'inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-slate-200 transition',
                            'hover:bg-white/[0.06] hover:text-white',
                            'disabled:cursor-not-allowed disabled:opacity-70',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                        )}
                        aria-label={actionLabel || 'Card actions'}
                    >
                        <HeaderAction variant={variant} spinning={actionBusy} />
                    </button>

                    {variant === 'regions' && menuOpen && actions.length ? (
                        <div
                            ref={menuRef}
                            className="absolute right-0 z-10 mt-2 w-44 overflow-hidden rounded-2xl border border-white/10 bg-[#0b0d14]/95 shadow-[0_20px_60px_rgba(0,0,0,0.65)] backdrop-blur"
                        >
                            <div className="p-2">
                                {actions.map((action) => (
                                    <button
                                        key={action.label}
                                        type="button"
                                        onClick={() => {
                                            setMenuOpen(false)
                                            action.onClick?.()
                                        }}
                                        className={cn(
                                            'flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-medium transition',
                                            'text-slate-200 hover:bg-white/[0.06] hover:text-white',
                                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                        )}
                                    >
                                        {action.icon ? <action.icon size={14} className="opacity-80" /> : null}
                                        {action.label}
                                    </button>
                                ))}
                            </div>
                        </div>
                    ) : null}
                </div>
            </div>

            <div className="mt-5 space-y-4">
                {rows.map((row) => {
                    if (variant === 'regions') {
                        return (
                            <button
                                key={`${row.code}-${row.label}`}
                                type="button"
                                onClick={() => onItemClick?.(row)}
                                className={cn(
                                    'w-full text-left transition',
                                    'rounded-xl px-2 py-1 -mx-2',
                                    'hover:bg-white/[0.04]',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                            >
                                <div className="space-y-2">
                                    <div className="flex items-center justify-between gap-3 text-xs">
                                        <div className="flex items-center gap-3 text-slate-200">
                                            <span className="w-7 text-[11px] font-semibold tracking-[0.18em] text-slate-400">{row.code}</span>
                                            <span className="text-slate-300">{row.label}</span>
                                        </div>
                                        <span className="font-semibold text-white">{row.value}%</span>
                                    </div>
                                    <div className="h-2 w-full rounded-full bg-white/[0.06]">
                                        <div
                                            className="h-2 rounded-full bg-cyan-400 shadow-[0_0_16px_rgba(34,211,238,0.18)]"
                                            style={{ width: `${row.value}%` }}
                                        />
                                    </div>
                                </div>
                            </button>
                        )
                    }

                    const Icon = SOURCE_ICON[row.key] || MessageCircle
                    const iconTone = TONE_CLASS[row.tone] || 'text-slate-300'

                    return (
                        <button
                            key={row.key}
                            type="button"
                            onClick={() => onItemClick?.(row)}
                            className={cn(
                                'w-full text-left transition',
                                'rounded-xl px-2 py-1 -mx-2',
                                'hover:bg-white/[0.04]',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                            )}
                        >
                            <div className="space-y-2">
                                <div className="flex items-center justify-between gap-3 text-xs">
                                    <div className="flex items-center gap-3 text-slate-200">
                                        <span className="grid h-9 w-9 place-items-center rounded-xl border border-white/10 bg-white/[0.04]">
                                            <Icon size={16} className={cn('opacity-90', iconTone)} />
                                        </span>
                                        <span className="text-slate-300">{row.label}</span>
                                    </div>
                                    <span className="font-semibold text-white">{row.value}%</span>
                                </div>
                                <div className="h-2 w-full rounded-full bg-white/[0.06]">
                                    <div
                                        className="h-2 rounded-full bg-cyan-400 shadow-[0_0_16px_rgba(34,211,238,0.18)]"
                                        style={{ width: `${row.value}%` }}
                                    />
                                </div>
                            </div>
                        </button>
                    )
                })}
            </div>
        </section>
    )
}
