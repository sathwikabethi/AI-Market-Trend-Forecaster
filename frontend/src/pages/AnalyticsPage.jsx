import { useEffect, useMemo, useRef, useState } from 'react'
import { Activity, Pause, Play, RefreshCw } from 'lucide-react'
import TopNav from '../components/TopNav'
import Skeleton from '../components/Skeleton'
import Spinner from '../components/Spinner'
import { cn } from '../lib/cn'

const nf = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 })

function asInt(value) {
    const n = Number(value || 0)
    if (!Number.isFinite(n)) return 0
    return Math.trunc(n)
}

function formatInt(value) {
    return nf.format(asInt(value))
}

function formatMs(value) {
    const n = Number(value || 0)
    if (!Number.isFinite(n) || n <= 0) return '0 ms'
    if (n >= 1000) return `${(n / 1000).toFixed(2)} s`
    return `${n.toFixed(0)} ms`
}

function StatusPill({ status }) {
    const tone = status === 'live'
        ? 'bg-emerald-400/15 text-emerald-200'
        : status === 'retrying'
            ? 'bg-amber-400/15 text-amber-200'
            : 'bg-slate-400/15 text-slate-200'
    const dot = status === 'live'
        ? 'bg-emerald-300'
        : status === 'retrying'
            ? 'bg-amber-300'
            : 'bg-slate-300'
    const label = status === 'live' ? 'Live' : status === 'retrying' ? 'Reconnecting' : 'Connecting'

    return (
        <span className={cn('inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold', tone)}>
            <span className={cn('h-2 w-2 rounded-full shadow-[0_0_16px_rgba(0,0,0,0.35)]', dot)} />
            {label}
        </span>
    )
}

function MetricCard({ label, value, helper }) {
    return (
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 shadow-[0_18px_45px_rgba(0,0,0,0.35)] backdrop-blur">
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">{label}</p>
            <p className="mt-3 text-2xl font-semibold tracking-tight text-white">{value}</p>
            {helper ? <p className="mt-2 text-xs text-slate-400">{helper}</p> : null}
        </div>
    )
}

export default function AnalyticsPage({ user, theme, onToggleTheme, onLogout }) {
    const isAdmin = String(user?.role || '').trim().toLowerCase() === 'admin'
    const sourceRef = useRef(null)

    const [paused, setPaused] = useState(false)
    const [intervalMs, setIntervalMs] = useState(2000)
    const [status, setStatus] = useState('connecting') // connecting | live | retrying
    const [snapshot, setSnapshot] = useState(null)
    const [lastErrorAt, setLastErrorAt] = useState(null)

    useEffect(() => {
        if (!isAdmin) return undefined
        if (paused) return undefined

        const url = `/api/admin/analytics/stream?interval_ms=${encodeURIComponent(intervalMs)}`
        const es = new EventSource(url)
        sourceRef.current = es
        setStatus('connecting')

        const onSnapshot = (event) => {
            try {
                const parsed = JSON.parse(event?.data || '{}')
                setSnapshot(parsed)
                setStatus('live')
            } catch {
                // Ignore malformed events.
            }
        }

        es.addEventListener('snapshot', onSnapshot)
        es.onopen = () => setStatus('live')
        es.onerror = () => {
            setLastErrorAt(new Date().toISOString())
            setStatus((prev) => (prev === 'live' ? 'retrying' : prev))
        }

        return () => {
            es.removeEventListener('snapshot', onSnapshot)
            es.close()
            sourceRef.current = null
        }
    }, [intervalMs, isAdmin, paused])

    const derived = useMemo(() => {
        const counters = snapshot?.metrics?.counters || {}
        const timings = snapshot?.metrics?.timings_ms_total || {}

        const requestsTotal = asInt(counters.http_requests_total)
        const avgLatencyMs = requestsTotal > 0
            ? Number(timings.http_response_time_ms_total || 0) / requestsTotal
            : 0

        const endpointCounts = Object.entries(counters)
            .filter(([key]) => key.startsWith('http_requests_') && key !== 'http_requests_total')
            .map(([key, value]) => ({ key, value: asInt(value) }))
            .sort((a, b) => b.value - a.value)
            .slice(0, 10)

        return {
            counters,
            timings,
            requestsTotal,
            avgLatencyMs,
            endpointCounts,
            cache: snapshot?.cache || {},
            queue: snapshot?.queue || {},
            rateLimit: snapshot?.rate_limit || {},
            ts: snapshot?.timestamp ? new Date(snapshot.timestamp) : null,
        }
    }, [snapshot])

    return (
        <div className="min-h-screen bg-tf-bg text-tf-fg">
            <TopNav user={user} theme={theme} onToggleTheme={onToggleTheme} onLogout={onLogout} />

            <main className="mx-auto w-full max-w-6xl px-4 pb-12 pt-8">
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                        <div className="flex items-center gap-3">
                            <div className="grid h-10 w-10 place-items-center rounded-2xl bg-gradient-to-br from-emerald-400 via-cyan-400 to-sky-500 shadow-[0_18px_50px_rgba(34,211,238,0.20)]">
                                <Activity size={18} className="text-slate-950" />
                            </div>
                            <h1 className="text-3xl font-semibold tracking-tight text-white">Realtime Analytics</h1>
                        </div>
                        <p className="mt-3 text-sm text-slate-400">
                            Live service metrics streamed from the backend. Admin-only.
                        </p>
                    </div>

                    <div className="flex flex-wrap items-center justify-end gap-2">
                        <StatusPill status={status} />

                        <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-2 shadow-[0_18px_45px_rgba(0,0,0,0.35)] backdrop-blur">
                            <RefreshCw size={16} className="text-slate-300" />
                            <select
                                value={intervalMs}
                                onChange={(e) => setIntervalMs(Number(e.target.value) || 2000)}
                                className={cn(
                                    'bg-transparent text-xs font-semibold text-slate-200',
                                    'focus-visible:outline-none',
                                )}
                            >
                                <option value={1000}>1s</option>
                                <option value={2000}>2s</option>
                                <option value={5000}>5s</option>
                                <option value={10000}>10s</option>
                            </select>
                        </div>

                        <button
                            type="button"
                            onClick={() => setPaused((v) => !v)}
                            className={cn(
                                'inline-flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-2 text-xs font-semibold text-slate-200',
                                'shadow-[0_18px_45px_rgba(0,0,0,0.35)] backdrop-blur transition hover:bg-white/[0.06] hover:text-white',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                            )}
                        >
                            {paused ? <Play size={16} /> : <Pause size={16} />}
                            {paused ? 'Resume' : 'Pause'}
                        </button>
                    </div>
                </div>

                {!isAdmin ? (
                    <section className="mt-6 rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-sm text-slate-300">
                        This page is available to admin users only.
                    </section>
                ) : !snapshot ? (
                    <section className="mt-6 grid gap-6 lg:grid-cols-3">
                        <div className="lg:col-span-3 rounded-2xl border border-white/10 bg-white/[0.03] p-6 shadow-[0_18px_45px_rgba(0,0,0,0.35)] backdrop-blur">
                            <Spinner label="Connecting to analytics stream..." />
                            {lastErrorAt ? (
                                <p className="mt-3 text-xs text-slate-400">Last error: {lastErrorAt}</p>
                            ) : null}
                        </div>
                        <Skeleton className="h-[110px]" />
                        <Skeleton className="h-[110px]" />
                        <Skeleton className="h-[110px]" />
                    </section>
                ) : (
                    <>
                        <section className="mt-6 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                            <MetricCard
                                label="Requests"
                                value={formatInt(derived.requestsTotal)}
                                helper={derived.ts ? `Last snapshot: ${derived.ts.toLocaleTimeString()}` : null}
                            />
                            <MetricCard
                                label="Avg Latency"
                                value={formatMs(derived.avgLatencyMs)}
                                helper="Approx. (total response time / total requests)."
                            />
                            <MetricCard
                                label="Rate Limit Keys"
                                value={formatInt(derived.rateLimit?.tracked_keys)}
                                helper="Number of client keys tracked in the in-memory limiter."
                            />

                            <MetricCard
                                label="Cache Hits"
                                value={formatInt(derived.cache?.hits)}
                                helper={`Size: ${formatInt(derived.cache?.size)} | Misses: ${formatInt(derived.cache?.misses)}`}
                            />
                            <MetricCard
                                label="Queue Depth"
                                value={formatInt(derived.queue?.redis_depth)}
                                helper={`Pending: ${formatInt(derived.queue?.db_pending_ready)} ready / ${formatInt(derived.queue?.db_pending_total)} total`}
                            />
                            <MetricCard
                                label="Redis Enabled"
                                value={derived.queue?.redis_enabled ? 'Yes' : 'No'}
                                helper={`Dead jobs: ${formatInt(derived.queue?.db_dead_total)}`}
                            />
                        </section>

                        <section className="mt-6 grid gap-6 lg:grid-cols-2">
                            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 shadow-[0_18px_45px_rgba(0,0,0,0.35)] backdrop-blur">
                                <p className="text-sm font-semibold text-white">Top Endpoints</p>
                                <p className="mt-1 text-xs text-slate-400">Most-requested paths (since process start).</p>

                                {!derived.endpointCounts.length ? (
                                    <p className="mt-4 text-sm text-slate-400">No endpoint metrics yet.</p>
                                ) : (
                                    <div className="mt-4 overflow-hidden rounded-2xl border border-white/10">
                                        {derived.endpointCounts.map((row) => (
                                            <div key={row.key} className="flex items-center justify-between gap-3 border-t border-white/10 bg-white/[0.02] px-4 py-3 first:border-t-0">
                                                <p className="truncate text-xs font-medium text-slate-200">{row.key.replace(/^http_requests_/, '')}</p>
                                                <p className="text-xs font-semibold text-white">{formatInt(row.value)}</p>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>

                            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 shadow-[0_18px_45px_rgba(0,0,0,0.35)] backdrop-blur">
                                <p className="text-sm font-semibold text-white">Raw Counters</p>
                                <p className="mt-1 text-xs text-slate-400">Useful for debugging API traffic and errors.</p>

                                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                                    {[
                                        ['HTTP 2xx', derived.counters.http_responses_200 ?? 0],
                                        ['HTTP 4xx', (derived.counters.http_responses_400 ?? 0) + (derived.counters.http_responses_401 ?? 0) + (derived.counters.http_responses_403 ?? 0) + (derived.counters.http_responses_404 ?? 0) + (derived.counters.http_responses_422 ?? 0) + (derived.counters.http_responses_429 ?? 0)],
                                        ['HTTP 5xx', derived.counters.http_responses_500 ?? 0],
                                        ['Rate limited', derived.counters.http_rate_limited_total ?? 0],
                                        ['Validation errors', derived.counters.http_validation_errors_total ?? 0],
                                        ['Unhandled errors', derived.counters.http_unhandled_errors_total ?? 0],
                                    ].map(([label, value]) => (
                                        <div key={label} className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
                                            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">{label}</p>
                                            <p className="mt-3 text-xl font-semibold text-white">{formatInt(value)}</p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </section>
                    </>
                )}
            </main>
        </div>
    )
}

