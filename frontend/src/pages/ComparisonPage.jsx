import { useEffect, useMemo, useState } from 'react'
import { ArrowLeftRight } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import KpiCard from '../components/KpiCard'
import SentimentCard from '../components/SentimentCard'
import Spinner from '../components/Spinner'
import TopNav from '../components/TopNav'
import TrendCard from '../components/TrendCard'
import { cn } from '../lib/cn'
import { getDashboardOverview } from '../lib/api'
import { BRAND_TABS } from '../lib/brands'

export default function ComparisonPage({ user, theme, onToggleTheme, onLogout }) {
    const products = useMemo(() => BRAND_TABS.filter((tab) => tab.id !== 'all'), [])
    const byId = useMemo(() => new Map(products.map((p) => [p.id, p.label])), [products])
    const [searchParams] = useSearchParams()

    const [left, setLeft] = useState('neutrogena')
    const [right, setRight] = useState('cerave')
    const [rangeDays, setRangeDays] = useState(7)

    const [loading, setLoading] = useState(true)
    const [leftModel, setLeftModel] = useState(null)
    const [rightModel, setRightModel] = useState(null)

    useEffect(() => {
        const leftParam = (searchParams.get('left') || '').trim().toLowerCase()
        const rightParam = (searchParams.get('right') || '').trim().toLowerCase()
        const daysParam = (searchParams.get('days') || '').trim()

        if (leftParam && byId.has(leftParam)) {
            setLeft(leftParam)
            if (rightParam && byId.has(rightParam) && rightParam !== leftParam) {
                setRight(rightParam)
            } else if (rightParam && rightParam === leftParam) {
                const fallback = Array.from(byId.keys()).find((id) => id !== leftParam) || 'cerave'
                setRight(fallback)
            }
        } else if (rightParam && byId.has(rightParam)) {
            setRight(rightParam)
        }

        const parsedDays = Number.parseInt(daysParam, 10)
        if ([7, 14, 30].includes(parsedDays)) setRangeDays(parsedDays)
    }, [byId, searchParams])

    useEffect(() => {
        let active = true
        setLoading(true)
        Promise.all([
            getDashboardOverview(left, rangeDays),
            getDashboardOverview(right, rangeDays),
        ])
            .then(([a, b]) => {
                if (!active) return
                setLeftModel(a)
                setRightModel(b)
            })
            .catch((err) => {
                if (!active) return
                setLeftModel(null)
                setRightModel(null)
                toast.error(err?.response?.data?.message || 'Comparison request failed.')
            })
            .finally(() => active && setLoading(false))

        return () => { active = false }
    }, [left, right, rangeDays])

    const leftLabel = byId.get(left) || left
    const rightLabel = byId.get(right) || right

    const trend = useMemo(() => {
        const a = leftModel?.trend?.line
        const b = rightModel?.trend?.line
        if (!a?.data?.length || !b?.data?.length) return null
        return {
            mode: 'multi',
            lines: [
                {
                    key: left,
                    label: leftLabel,
                    color: '#22d3ee',
                    data: a.data,
                },
                {
                    key: right,
                    label: rightLabel,
                    color: '#a855f7',
                    data: b.data,
                },
            ],
        }
    }, [left, leftLabel, leftModel, right, rightLabel, rightModel])

    return (
        <div className="min-h-screen bg-tf-bg text-tf-fg">
            <TopNav user={user} theme={theme} onToggleTheme={onToggleTheme} onLogout={onLogout} />

            <main className="mx-auto w-full max-w-6xl px-4 pb-12 pt-8">
                <h1 className="text-3xl font-semibold tracking-tight text-white">Comparison</h1>
                <p className="mt-2 text-sm text-slate-400">
                    Side-by-side brand and trend comparisons.
                </p>

                <section className="mt-6 rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-white/[0.03] p-6 shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur">
                    <div className="grid gap-4 md:grid-cols-[1fr_auto_1fr] md:items-end">
                        <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Product A</p>
                            <select
                                value={left}
                                onChange={(event) => {
                                    const next = event.target.value
                                    setLeft(next)
                                    if (next === right) setRight(left)
                                }}
                                className={cn(
                                    'mt-3 w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-semibold text-slate-200',
                                    'shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] transition hover:bg-white/[0.06] hover:text-white',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                            >
                                {products.map((p) => (
                                    <option key={p.id} value={p.id}>{p.label}</option>
                                ))}
                            </select>
                        </div>

                        <div className="flex flex-col items-center gap-2">
                            <button
                                type="button"
                                onClick={() => {
                                    setLeft(right)
                                    setRight(left)
                                }}
                                className={cn(
                                    'inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-slate-200 transition',
                                    'hover:bg-white/[0.06] hover:text-white',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                                aria-label="Swap products"
                            >
                                <ArrowLeftRight size={18} />
                            </button>
                            <div className="flex flex-wrap gap-2">
                                {[7, 14, 30].map((days) => (
                                    <button
                                        key={days}
                                        type="button"
                                        onClick={() => setRangeDays(days)}
                                        className={cn(
                                            'rounded-full px-3 py-1 text-[11px] font-semibold transition',
                                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                            rangeDays === days
                                                ? 'bg-white/[0.08] text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.10)]'
                                                : 'border border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.06] hover:text-white',
                                        )}
                                    >
                                        {days}d
                                    </button>
                                ))}
                            </div>
                        </div>

                        <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Product B</p>
                            <select
                                value={right}
                                onChange={(event) => {
                                    const next = event.target.value
                                    setRight(next)
                                    if (next === left) setLeft(right)
                                }}
                                className={cn(
                                    'mt-3 w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-semibold text-slate-200',
                                    'shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] transition hover:bg-white/[0.06] hover:text-white',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                            >
                                {products.map((p) => (
                                    <option key={p.id} value={p.id}>{p.label}</option>
                                ))}
                            </select>
                        </div>
                    </div>
                </section>

                {!trend || !leftModel || !rightModel ? (
                    <section className="mt-6 rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-sm text-slate-400">
                        {loading ? <Spinner label="Loading comparison..." /> : 'No comparison data available yet.'}
                    </section>
                ) : (
                    <>
                        <section className={cn('mt-6', loading && 'opacity-80')}>
                            <TrendCard
                                title="Sentiment Trend Comparison"
                                subtitle={`${rangeDays}-Day Trailing Overview`}
                                trend={trend}
                            />
                        </section>

                        <section className={cn('mt-6 grid gap-6 lg:grid-cols-2', loading && 'opacity-80')}>
                            <div className="space-y-6">
                                <div className="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4">
                                    <p className="text-sm font-semibold text-white">{leftLabel}</p>
                                    <span className="h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_16px_rgba(34,211,238,0.18)]" />
                                </div>
                                <div className="grid gap-6 sm:grid-cols-3 lg:grid-cols-1">
                                    {(leftModel.kpis || []).map((kpi) => (
                                        <KpiCard
                                            key={`${left}-${kpi.label}`}
                                            helper={kpi.helper}
                                            label={kpi.label}
                                            value={kpi.value}
                                            progress={kpi.progress}
                                            accent={kpi.accent}
                                        />
                                    ))}
                                </div>
                                <SentimentCard
                                    sentiment={leftModel.sentiment}
                                    onViewAll={() => toast(`${leftLabel}: sentiment breakdown`)}
                                />
                            </div>

                            <div className="space-y-6">
                                <div className="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4">
                                    <p className="text-sm font-semibold text-white">{rightLabel}</p>
                                    <span className="h-2 w-2 rounded-full bg-violet-400 shadow-[0_0_16px_rgba(168,85,247,0.18)]" />
                                </div>
                                <div className="grid gap-6 sm:grid-cols-3 lg:grid-cols-1">
                                    {(rightModel.kpis || []).map((kpi) => (
                                        <KpiCard
                                            key={`${right}-${kpi.label}`}
                                            helper={kpi.helper}
                                            label={kpi.label}
                                            value={kpi.value}
                                            progress={kpi.progress}
                                            accent={kpi.accent}
                                        />
                                    ))}
                                </div>
                                <SentimentCard
                                    sentiment={rightModel.sentiment}
                                    onViewAll={() => toast(`${rightLabel}: sentiment breakdown`)}
                                />
                            </div>
                        </section>
                    </>
                )}
            </main>
        </div>
    )
}
