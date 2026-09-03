import { useEffect, useMemo, useRef, useState } from 'react'
import {
    MessageCircle,
    Newspaper,
    RefreshCcw,
    RotateCcw,
    Star,
    Twitter,
} from 'lucide-react'
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

function clampInt(value, lo, hi) {
    const safe = Number.isFinite(Number(value)) ? Number(value) : 0
    return Math.max(lo, Math.min(hi, Math.round(safe)))
}

function rebalance(values, changedKey, nextValue) {
    const next = { ...(values || {}) }
    const keys = Object.keys(next)
    if (!keys.length || !changedKey) return next

    const clamped = clampInt(nextValue, 0, 100)
    next[changedKey] = clamped

    const others = keys.filter((k) => k !== changedKey)
    const remaining = 100 - clamped
    if (!others.length) return { [changedKey]: 100 }

    const totalOther = others.reduce((sum, k) => sum + clampInt(next[k], 0, 100), 0)
    let used = 0
    for (let idx = 0; idx < others.length; idx += 1) {
        const key = others[idx]
        if (idx === others.length - 1) {
            next[key] = Math.max(0, remaining - used)
            break
        }
        const share = totalOther > 0
            ? Math.round((clampInt(next[key], 0, 100) / totalOther) * remaining)
            : Math.round(remaining / others.length)
        const value = clampInt(share, 0, remaining)
        next[key] = value
        used += value
    }
    return next
}

export default function DataSourcesCard({
    title = 'Data Sources',
    items,
    onRefresh,
    refreshing = false,
    onItemClick,
    onMixChange,
}) {
    const rows = useMemo(() => (Array.isArray(items) ? items : []), [items])

    const initial = useMemo(() => {
        const next = {}
        for (const row of rows) {
            const key = String(row?.key || '').trim()
            if (!key) continue
            next[key] = clampInt(row?.value ?? 0, 0, 100)
        }
        return next
    }, [rows])

    const [values, setValues] = useState(initial)
    const [isDirty, setDirty] = useState(false)
    const dragKeyRef = useRef(null)

    useEffect(() => {
        setValues(initial)
        setDirty(false)
    }, [initial])

    const handleSet = (key, nextValue) => {
        setValues((current) => {
            const next = rebalance(current, key, nextValue)
            onMixChange?.(next, true)
            return next
        })
        setDirty(true)
    }

    return (
        <section className="rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-white/[0.03] p-5 shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur">
            <div className="flex items-center justify-between gap-3">
                <div>
                    <h3 className="text-sm font-semibold text-white">{title}</h3>
                    {isDirty ? (
                        <p className="mt-1 text-[11px] text-slate-400">Simulated mix (drag bars to adjust)</p>
                    ) : null}
                </div>
                <div className="flex items-center gap-2">
                    <button
                        type="button"
                        onClick={() => {
                            setValues(initial)
                            setDirty(false)
                            onMixChange?.(initial, false)
                        }}
                        aria-label="Reset source mix"
                        className={cn(
                            'inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-slate-200 transition',
                            'hover:bg-white/[0.06] hover:text-white',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                        )}
                    >
                        <RotateCcw size={16} className="text-slate-400" />
                    </button>
                    <button
                        type="button"
                        onClick={() => onRefresh?.({ mix: values, dirty: isDirty })}
                        disabled={refreshing}
                        aria-label="Refresh data sources"
                        className={cn(
                            'inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-slate-200 transition',
                            'hover:bg-white/[0.06] hover:text-white',
                            'disabled:cursor-not-allowed disabled:opacity-70',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                        )}
                    >
                        <RefreshCcw size={16} className={cn('text-slate-400', refreshing && 'animate-spin')} />
                    </button>
                </div>
            </div>

            <div className="mt-5 space-y-4">
                {rows.map((row) => {
                    const Icon = SOURCE_ICON[row.key] || MessageCircle
                    const iconTone = TONE_CLASS[row.tone] || 'text-slate-300'
                    const value = clampInt(values?.[row.key] ?? row.value, 0, 100)

                    return (
                        <div key={row.key} className="space-y-2">
                            <div className="flex items-center justify-between gap-3 text-xs">
                                <button
                                    type="button"
                                    onClick={() => onItemClick?.(row)}
                                    className={cn(
                                        'flex items-center gap-3 text-slate-200 transition',
                                        'rounded-xl px-2 py-1 -mx-2',
                                        'hover:bg-white/[0.04] hover:text-white',
                                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                    )}
                                >
                                    <span className="grid h-9 w-9 place-items-center rounded-xl border border-white/10 bg-white/[0.04]">
                                        <Icon size={16} className={cn('opacity-90', iconTone)} />
                                    </span>
                                    <span className="text-slate-300">{row.label}</span>
                                </button>
                                <span className="font-semibold text-white">{value}%</span>
                            </div>

                            <div
                                className="relative h-2 w-full rounded-full bg-white/[0.06]"
                                onPointerDown={(event) => {
                                    dragKeyRef.current = row.key
                                    event.currentTarget.setPointerCapture(event.pointerId)

                                    const rect = event.currentTarget.getBoundingClientRect()
                                    const pct = ((event.clientX - rect.left) / Math.max(1, rect.width)) * 100
                                    handleSet(row.key, pct)
                                }}
                                onPointerMove={(event) => {
                                    if (dragKeyRef.current !== row.key) return
                                    const rect = event.currentTarget.getBoundingClientRect()
                                    const pct = ((event.clientX - rect.left) / Math.max(1, rect.width)) * 100
                                    handleSet(row.key, pct)
                                }}
                                onPointerUp={() => { dragKeyRef.current = null }}
                                onPointerCancel={() => { dragKeyRef.current = null }}
                                role="slider"
                                aria-label={`${row.label} share`}
                                aria-valuemin={0}
                                aria-valuemax={100}
                                aria-valuenow={value}
                                tabIndex={0}
                                onKeyDown={(event) => {
                                    if (event.key === 'ArrowLeft') handleSet(row.key, value - 1)
                                    if (event.key === 'ArrowRight') handleSet(row.key, value + 1)
                                    if (event.key === 'Home') handleSet(row.key, 0)
                                    if (event.key === 'End') handleSet(row.key, 100)
                                }}
                            >
                                <div
                                    className="h-2 rounded-full bg-cyan-400 shadow-[0_0_16px_rgba(34,211,238,0.18)]"
                                    style={{ width: `${value}%` }}
                                />
                                <div
                                    className={cn(
                                        'absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full border border-white/20 bg-[#0b0d14]',
                                        'shadow-[0_10px_30px_rgba(0,0,0,0.55)]',
                                    )}
                                    style={{ left: `calc(${value}% - 8px)` }}
                                />
                            </div>
                        </div>
                    )
                })}
            </div>
        </section>
    )
}
