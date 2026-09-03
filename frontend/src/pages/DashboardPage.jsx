import { useEffect, useMemo, useRef, useState } from 'react'
import { Copy, Download, GitCompare, Settings2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import IconButton from '../components/IconButton'
import KpiCard from '../components/KpiCard'
import DataSourcesCard from '../components/DataSourcesCard'
import Modal from '../components/Modal'
import ProgressListCard from '../components/ProgressListCard'
import SentimentCard from '../components/SentimentCard'
import Spinner from '../components/Spinner'
import TopNav from '../components/TopNav'
import TrendingTopicsCard from '../components/TrendingTopicsCard'
import TrendCard from '../components/TrendCard'
import { cn } from '../lib/cn'
import { getDashboardOverview, getDashboardReviews } from '../lib/api'
import { BRAND_TABS } from '../lib/brands'
import { exportChartAsPng, exportChartAsSvg, openPrintPdfWindow } from '../lib/chart_export'
import { downloadTextFile, toCsv } from '../lib/download'

const AUTO_REFRESH_KEY = 'tf_auto_refresh'
const NOTIFY_KEY = 'tf_notification_prefs'

function FilterPill({ active, children, ...props }) {
    return (
        <button
            type="button"
            className={cn(
                'rounded-full px-4 py-2 text-xs font-semibold transition',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                active
                    ? 'bg-gradient-to-r from-cyan-400 to-sky-500 text-slate-950 shadow-[0_0_0_1px_rgba(34,211,238,0.30),0_18px_45px_rgba(34,211,238,0.16)]'
                    : 'border border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.06] hover:text-white',
            )}
            {...props}
        >
            {children}
        </button>
    )
}

export default function DashboardPage({ user, theme, onToggleTheme, onLogout }) {
    const navigate = useNavigate()
    const [brand, setBrand] = useState('all')
    const [rangeDays, setRangeDays] = useState(7)
    const [selectedTopic, setSelectedTopic] = useState(null)
    const [sourceMix, setSourceMix] = useState(null)
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [model, setModel] = useState(null)
    const [settingsOpen, setSettingsOpen] = useState(false)
    const [draftDays, setDraftDays] = useState(7)
    const [sentimentOpen, setSentimentOpen] = useState(false)
    const [drillOpen, setDrillOpen] = useState(false)
    const [drillTitle, setDrillTitle] = useState('')
    const [drillRows, setDrillRows] = useState([])
    const [drillLoading, setDrillLoading] = useState(false)
    const [lastUpdated, setLastUpdated] = useState(null)
    const [autoRefresh, setAutoRefresh] = useState(() => localStorage.getItem(AUTO_REFRESH_KEY) === '1')
    const [downloadOpen, setDownloadOpen] = useState(false)

    const trendRef = useRef(null)
    const downloadRef = useRef(null)
    const mixTimerRef = useRef(null)
    const pendingMixRef = useRef(null)
    const fetchSeqRef = useRef(0)

    const sourceMixKey = useMemo(() => {
        if (!sourceMix) return ''
        return Object.entries(sourceMix)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([k, v]) => `${k}:${Math.round(Number(v) || 0)}`)
            .join(',')
    }, [sourceMix])

    const anomalyAlertsEnabled = useMemo(() => {
        try {
            const raw = localStorage.getItem(NOTIFY_KEY)
            const prefs = raw ? JSON.parse(raw) : {}
            return prefs?.anomalyAlerts !== false
        } catch {
            return true
        }
    }, [])

    useEffect(() => {
        localStorage.setItem(AUTO_REFRESH_KEY, autoRefresh ? '1' : '0')
    }, [autoRefresh])

    useEffect(() => {
        if (!downloadOpen) return undefined

        const handler = (event) => {
            const target = event.target
            if (!downloadRef.current) return
            if (downloadRef.current.contains(target)) return
            setDownloadOpen(false)
        }

        document.addEventListener('mousedown', handler)
        return () => document.removeEventListener('mousedown', handler)
    }, [downloadOpen])

    useEffect(() => () => {
        if (mixTimerRef.current) window.clearTimeout(mixTimerRef.current)
    }, [])

    useEffect(() => {
        if (!downloadOpen) return undefined
        const handler = (event) => {
            if (event.key === 'Escape') setDownloadOpen(false)
        }
        document.addEventListener('keydown', handler)
        return () => document.removeEventListener('keydown', handler)
    }, [downloadOpen])

    const requestOverview = async ({ refresh = false, showToast = false, nextMix = sourceMix } = {}) => {
        const seq = fetchSeqRef.current + 1
        fetchSeqRef.current = seq
        setLoading(true)
        try {
            const payload = await getDashboardOverview(brand, rangeDays, {
                topic: selectedTopic,
                refresh,
                sourceMix: nextMix,
            })
            if (fetchSeqRef.current !== seq) return
            setModel(payload)
            setLastUpdated(new Date())
            if (showToast) toast.success(refresh ? 'Dashboard refreshed.' : 'Dashboard updated.')
        } catch (err) {
            if (fetchSeqRef.current !== seq) return
            setModel(null)
            if (showToast) toast.error(err?.response?.data?.message || 'Refresh failed.')
        } finally {
            if (fetchSeqRef.current === seq) setLoading(false)
        }
    }

    useEffect(() => {
        requestOverview({ refresh: false, showToast: false })
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [brand, rangeDays, selectedTopic, sourceMixKey])

    useEffect(() => {
        if (!autoRefresh) return undefined
        const interval = window.setInterval(() => {
            requestOverview({ refresh: true, showToast: false })
        }, 30000)
        return () => window.clearInterval(interval)
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [autoRefresh, brand, rangeDays, selectedTopic, sourceMixKey])

    const viewModel = useMemo(() => {
        if (!model) return null
        const sentiment = model.sentiment ? { ...model.sentiment } : null
        if (sentiment) {
            sentiment.centerValue = sentiment.centerValue ?? sentiment.center_value
            sentiment.centerLabel = sentiment.centerLabel ?? sentiment.center_label
        }
        return { ...model, sentiment }
    }, [model])

    const productLabel = BRAND_TABS.find((tab) => tab.id === brand)?.label || 'All'
    const activeTopic = (selectedTopic || '').trim()

    const anomaly = useMemo(() => {
        const trend = viewModel?.trend
        if (!trend) return null

        const lines = trend?.mode === 'multi' ? (trend?.lines || []) : (trend?.line ? [trend.line] : [])
        if (!lines.length) return null

        let best = null
        for (const line of lines) {
            const data = Array.isArray(line?.data) ? line.data : []
            if (data.length < 6) continue
            const values = data.map((row) => Number(row?.value) || 0)
            const last = values[values.length - 1]
            const prev = values.slice(0, -1)
            const baseline = prev.reduce((sum, v) => sum + v, 0) / Math.max(1, prev.length)
            const diff = last - baseline
            const magnitude = Math.abs(diff)
            if (magnitude < 12) continue
            if (!best || magnitude > best.magnitude) {
                best = {
                    key: line?.key || '',
                    label: line?.label || line?.key || 'Trend',
                    kind: diff >= 0 ? 'spike' : 'drop',
                    magnitude,
                    diff,
                    last,
                    baseline,
                }
            }
        }
        return best
    }, [viewModel?.trend])

    const refreshDashboard = async (payload = null) => {
        const isDirty = Boolean(payload?.dirty)
        let nextMix = sourceMix

        if (payload && 'dirty' in payload) {
            if (!isDirty) {
                setSourceMix(null)
                nextMix = null
            }
            if (isDirty && payload?.mix) {
                setSourceMix(payload.mix)
                nextMix = payload.mix
            }
        }

        setRefreshing(true)
        try {
            await requestOverview({ refresh: true, showToast: true, nextMix })
        } finally {
            setRefreshing(false)
        }
    }

    const openDrilldown = async ({ title, filters, productOverride }) => {
        setDrillTitle(title || 'Reviews')
        setDrillOpen(true)
        setDrillRows([])
        setDrillLoading(true)
        try {
            const rows = await getDashboardReviews({
                product: productOverride ?? brand,
                days: rangeDays,
                topic: activeTopic || null,
                limit: 80,
                ...(filters || {}),
            })
            setDrillRows(rows)
        } catch (err) {
            toast.error(err?.response?.data?.message || 'Failed to load reviews.')
            setDrillRows([])
        } finally {
            setDrillLoading(false)
        }
    }

    const downloadReport = () => {
        if (!viewModel) {
            toast.error('Dashboard data is still loading.')
            return
        }

        const stamp = new Date().toISOString().replaceAll(':', '').replaceAll('-', '').slice(0, 15)
        const safeBrand = (brand || 'all').replaceAll(' ', '_')
        const report = {
            generated_at: new Date().toISOString(),
            filters: {
                product: brand,
                range_days: rangeDays,
                topic: activeTopic || null,
                source_mix: sourceMix || null,
            },
            snapshot: viewModel,
        }

        downloadTextFile(
            JSON.stringify(report, null, 2),
            `trendforecast_report_${safeBrand}_${rangeDays}d_${stamp}.json`,
            'application/json;charset=utf-8',
        )
        toast.success('Downloaded report snapshot.')
    }

    const downloadRegionsCsv = () => {
        if (!viewModel) return
        const rows = (viewModel.regions || []).map((row) => ({
            code: row.code,
            region: row.label,
            percent: row.value,
        }))
        downloadTextFile(toCsv(rows), `mentions_by_region_${brand}_${rangeDays}d.csv`, 'text/csv;charset=utf-8')
        toast.success('Downloaded regions CSV.')
    }

    const copyRegionsJson = async () => {
        if (!viewModel) return
        try {
            await navigator.clipboard.writeText(JSON.stringify(viewModel.regions || [], null, 2))
            toast.success('Copied regions JSON.')
        } catch {
            toast.error('Copy failed (browser blocked clipboard).')
        }
    }

    return (
        <div className="min-h-screen bg-tf-bg text-tf-fg">
            <TopNav user={user} theme={theme} onToggleTheme={onToggleTheme} onLogout={onLogout} />

            <main className="mx-auto w-full max-w-6xl px-4 pb-12 pt-8">
                <header>
                    <h1 className="text-3xl font-semibold tracking-tight text-white">
                        Market Sentiment Overview
                    </h1>
                    <p className="mt-2 text-sm text-slate-400">
                        Real-time consumer sentiment analysis across products
                    </p>
                </header>

                <div className="mt-7 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                    <div className="flex flex-wrap items-center gap-2">
                        {BRAND_TABS.map((tab) => (
                            <FilterPill
                                key={tab.id}
                                active={tab.id === brand}
                                onClick={() => {
                                    setBrand(tab.id)
                                    setSelectedTopic(null)
                                }}
                            >
                                {tab.label}
                            </FilterPill>
                        ))}
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="hidden flex-col items-end gap-1 md:flex">
                            <button
                                type="button"
                                onClick={() => setAutoRefresh((v) => !v)}
                                className={cn(
                                    'rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[11px] font-semibold text-slate-200 transition',
                                    'hover:bg-white/[0.06] hover:text-white',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                            >
                                Auto-refresh: {autoRefresh ? 'On' : 'Off'}
                            </button>
                            <p className="text-[11px] text-slate-500">
                                Last updated: {lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : '...'}
                            </p>
                        </div>

                        <div className="flex items-center gap-2" ref={downloadRef}>
                            <div className="relative">
                                <IconButton
                                    label="Downloads"
                                    onClick={() => setDownloadOpen((v) => !v)}
                                >
                                    <Download size={18} />
                                </IconButton>

                                {downloadOpen ? (
                                    <div className="absolute right-0 z-20 mt-2 w-56 overflow-hidden rounded-2xl border border-white/10 bg-[#0b0d14]/95 shadow-[0_20px_60px_rgba(0,0,0,0.65)] backdrop-blur">
                                        <div className="p-2">
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    setDownloadOpen(false)
                                                    downloadReport()
                                                }}
                                                className={cn(
                                                    'flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-medium transition',
                                                    'text-slate-200 hover:bg-white/[0.06] hover:text-white',
                                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                                )}
                                            >
                                                Download snapshot (JSON)
                                            </button>
                                            <button
                                                type="button"
                                                onClick={async () => {
                                                    setDownloadOpen(false)
                                                    try {
                                                        await exportChartAsPng(trendRef.current, `trend_${brand}_${rangeDays}d.png`)
                                                        toast.success('Exported chart PNG.')
                                                    } catch (err) {
                                                        toast.error(err?.message || 'Export failed.')
                                                    }
                                                }}
                                                className={cn(
                                                    'flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-medium transition',
                                                    'text-slate-200 hover:bg-white/[0.06] hover:text-white',
                                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                                )}
                                            >
                                                Export chart (PNG)
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    setDownloadOpen(false)
                                                    try {
                                                        exportChartAsSvg(trendRef.current, `trend_${brand}_${rangeDays}d.svg`)
                                                        toast.success('Exported chart SVG.')
                                                    } catch (err) {
                                                        toast.error(err?.message || 'Export failed.')
                                                    }
                                                }}
                                                className={cn(
                                                    'flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-medium transition',
                                                    'text-slate-200 hover:bg-white/[0.06] hover:text-white',
                                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                                )}
                                            >
                                                Export chart (SVG)
                                            </button>
                                            <button
                                                type="button"
                                                onClick={async () => {
                                                    setDownloadOpen(false)
                                                    try {
                                                        await openPrintPdfWindow({
                                                            title: 'Market Sentiment Overview',
                                                            subtitle: `${productLabel} - ${rangeDays}d`,
                                                            rootElement: trendRef.current,
                                                            meta: lastUpdated
                                                                ? `Last updated ${new Date(lastUpdated).toLocaleString()}`
                                                                : '',
                                                        })
                                                    } catch (err) {
                                                        toast.error(err?.message || 'PDF export failed.')
                                                    }
                                                }}
                                                className={cn(
                                                    'flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-medium transition',
                                                    'text-slate-200 hover:bg-white/[0.06] hover:text-white',
                                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                                )}
                                            >
                                                Print / Save as PDF
                                            </button>
                                        </div>
                                    </div>
                                ) : null}
                            </div>

                            <IconButton
                                label="Compare this brand"
                                onClick={() => {
                                    const left = brand && brand !== 'all' ? brand : 'neutrogena'
                                    navigate(`/comparison?left=${encodeURIComponent(left)}`)
                                }}
                            >
                                <GitCompare size={18} />
                            </IconButton>

                            <IconButton
                                label="Dashboard settings"
                                onClick={() => {
                                    setDraftDays(rangeDays)
                                    setSettingsOpen(true)
                                }}
                            >
                                <Settings2 size={18} />
                            </IconButton>
                        </div>
                    </div>
                </div>

                {activeTopic ? (
                    <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-slate-400">
                        <span className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-cyan-200">
                            Topic filter: {activeTopic}
                        </span>
                        <button
                            type="button"
                            onClick={() => setSelectedTopic(null)}
                            className={cn(
                                'rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 font-semibold text-slate-200 transition',
                                'hover:bg-white/[0.06] hover:text-white',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                            )}
                        >
                            Clear
                        </button>
                    </div>
                ) : null}

                {anomaly && anomalyAlertsEnabled ? (
                    <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 shadow-[0_20px_60px_rgba(0,0,0,0.25)] backdrop-blur">
                        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                            <div>
                                <p className="text-sm font-semibold text-white">
                                    Anomaly alert: {anomaly.label}
                                </p>
                                <p className="mt-1 text-xs text-slate-400">
                                    Sentiment {anomaly.kind === 'spike' ? 'spiked' : 'dropped'} by {Math.round(Math.abs(anomaly.diff))} points vs recent baseline.
                                </p>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                <button
                                    type="button"
                                    onClick={() => openDrilldown({
                                        title: `Anomaly - ${anomaly.label}`,
                                        productOverride: anomaly.key || brand,
                                        filters: {},
                                    })}
                                    className={cn(
                                        'rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-slate-200 transition',
                                        'hover:bg-white/[0.06] hover:text-white',
                                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                    )}
                                >
                                    Open reviews
                                </button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        const left = anomaly.key || (brand && brand !== 'all' ? brand : 'neutrogena')
                                        navigate(`/comparison?left=${encodeURIComponent(left)}`)
                                    }}
                                    className={cn(
                                        'rounded-full bg-gradient-to-r from-cyan-400 to-sky-500 px-4 py-2 text-xs font-semibold text-slate-950 transition',
                                        'shadow-[0_0_0_1px_rgba(34,211,238,0.30),0_18px_45px_rgba(34,211,238,0.16)] hover:brightness-105',
                                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                    )}
                                >
                                    Compare
                                </button>
                            </div>
                        </div>
                    </div>
                ) : null}

                {!viewModel ? (
                    <section className="mt-10 rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-sm text-slate-400">
                        {loading ? <Spinner label="Loading dashboard metrics..." /> : 'No dashboard data available yet.'}
                    </section>
                ) : (
                    <>
                        <section className={cn('mt-6 grid gap-6 lg:grid-cols-[320px_1fr]', loading && 'opacity-80')}>
                            <div className="flex flex-col gap-6">
                                {viewModel.kpis.map((kpi) => (
                                    <KpiCard
                                        key={kpi.label}
                                        helper={kpi.helper}
                                        label={kpi.label}
                                        value={kpi.value}
                                        progress={kpi.progress}
                                        accent={kpi.accent}
                                    />
                                ))}
                            </div>
                            <div ref={trendRef}>
                                <TrendCard title={viewModel.title} subtitle={viewModel.subtitle} trend={viewModel.trend} />
                            </div>
                        </section>

                        <section className={cn('mt-6 grid gap-6 lg:grid-cols-3', loading && 'opacity-80')}>
                            <SentimentCard sentiment={viewModel.sentiment} onViewAll={() => setSentimentOpen(true)} />
                            <ProgressListCard
                                title="Mentions by Region"
                                variant="regions"
                                items={viewModel.regions}
                                actionLabel="Region actions"
                                onItemClick={(row) => {
                                    openDrilldown({
                                        title: `Mentions by Region - ${row?.label || row?.code || ''}`,
                                        filters: { region: row?.code },
                                    })
                                }}
                                menuActions={[
                                    { label: 'Download CSV', icon: Download, onClick: downloadRegionsCsv },
                                    { label: 'Copy JSON', icon: Copy, onClick: copyRegionsJson },
                                ]}
                            />
                            <DataSourcesCard
                                title="Data Sources"
                                items={viewModel.sources}
                                onRefresh={refreshDashboard}
                                refreshing={refreshing}
                                onMixChange={(mix, dirty) => {
                                    if (mixTimerRef.current) window.clearTimeout(mixTimerRef.current)
                                    pendingMixRef.current = { mix, dirty }
                                    mixTimerRef.current = window.setTimeout(() => {
                                        const payload = pendingMixRef.current
                                        if (!payload) return
                                        if (!payload.dirty) {
                                            setSourceMix(null)
                                            return
                                        }
                                        setSourceMix(payload.mix)
                                    }, 420)
                                }}
                                onItemClick={(row) => {
                                    openDrilldown({
                                        title: `Data Sources - ${row?.label || row?.key || ''}`,
                                        filters: { source: row?.key },
                                    })
                                }}
                            />
                        </section>

                        <TrendingTopicsCard
                            topics={viewModel.topics}
                            selectedTopic={selectedTopic}
                            onToggleTopic={(topic) => {
                                const next = String(topic?.label || '').trim()
                                if (!next) return
                                setSelectedTopic((current) => {
                                    const isSame = String(current || '').toLowerCase() === next.toLowerCase()
                                    const value = isSame ? null : next
                                    toast(isSame ? 'Topic filter cleared.' : `Filtering: ${productLabel} - ${next}`)
                                    if (!isSame) {
                                        openDrilldown({
                                            title: `Trending Topic - ${next}`,
                                            filters: { topic: next },
                                        })
                                    }
                                    return value
                                })
                            }}
                        />
                    </>
                )}
            </main>

            <Modal
                open={settingsOpen}
                title="Dashboard settings"
                description="Adjust the time window for the current dashboard view."
                onClose={() => setSettingsOpen(false)}
            >
                <div className="space-y-5">
                    <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                            Time window
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                            {[7, 14, 30].map((days) => (
                                <button
                                    key={days}
                                    type="button"
                                    onClick={() => setDraftDays(days)}
                                    className={cn(
                                        'rounded-full px-4 py-2 text-xs font-semibold transition',
                                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                        draftDays === days
                                            ? 'bg-gradient-to-r from-cyan-400 to-sky-500 text-slate-950 shadow-[0_0_0_1px_rgba(34,211,238,0.30),0_18px_45px_rgba(34,211,238,0.16)]'
                                            : 'border border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.06] hover:text-white',
                                    )}
                                >
                                    Last {days} days
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="text-xs text-slate-400">
                            Current view: <span className="font-semibold text-slate-200">{productLabel}</span>
                        </p>
                        <button
                            type="button"
                            onClick={refreshDashboard}
                            disabled={refreshing}
                            className={cn(
                                'rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-slate-200 transition',
                                'hover:bg-white/[0.06] hover:text-white',
                                'disabled:cursor-not-allowed disabled:opacity-70',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                            )}
                        >
                            Refresh now
                        </button>
                    </div>

                    <div className="flex justify-end gap-2">
                        <button
                            type="button"
                            onClick={() => setSettingsOpen(false)}
                            className={cn(
                                'rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-slate-200 transition',
                                'hover:bg-white/[0.06] hover:text-white',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                            )}
                        >
                            Cancel
                        </button>
                        <button
                            type="button"
                            onClick={() => {
                                setRangeDays(draftDays)
                                setSettingsOpen(false)
                                toast.success(`Updated dashboard window to last ${draftDays} days.`)
                            }}
                            className={cn(
                                'rounded-full bg-gradient-to-r from-cyan-400 to-sky-500 px-4 py-2 text-xs font-semibold text-slate-950 transition',
                                'shadow-[0_0_0_1px_rgba(34,211,238,0.30),0_18px_45px_rgba(34,211,238,0.16)]',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                            )}
                        >
                            Apply
                        </button>
                    </div>
                </div>
            </Modal>

            <Modal
                open={sentimentOpen}
                title="Sentiment distribution"
                description="Breakdown of the current dashboard view."
                onClose={() => setSentimentOpen(false)}
                className="max-w-xl"
            >
                {!viewModel ? (
                    <p className="text-sm text-slate-400">No sentiment data available.</p>
                ) : (
                    <div className="space-y-4">
                        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                            <p className="text-xs text-slate-400">Center value</p>
                            <p className="mt-1 text-lg font-semibold text-white">
                                {viewModel.sentiment?.centerValue ?? viewModel.sentiment?.center_value}
                                <span className="ml-2 text-xs font-medium text-slate-400">
                                    {viewModel.sentiment?.centerLabel ?? viewModel.sentiment?.center_label}
                                </span>
                            </p>
                        </div>
                        <div className="space-y-3">
                            {(viewModel.sentiment?.items || []).map((item) => (
                                <div key={item.label} className="space-y-2">
                                    <div className="flex items-center justify-between gap-3 text-xs">
                                        <div className="flex items-center gap-2 text-slate-300">
                                            <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
                                            <span>{item.label}</span>
                                        </div>
                                        <span className="font-semibold text-white">{item.value}%</span>
                                    </div>
                                    <div className="h-2 w-full rounded-full bg-white/[0.06]">
                                        <div
                                            className="h-2 rounded-full shadow-[0_0_16px_rgba(34,211,238,0.18)]"
                                            style={{ width: `${item.value}%`, background: item.color }}
                                        />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </Modal>

            <Modal
                open={drillOpen}
                title={drillTitle || 'Reviews'}
                description="Underlying reviews for the selected drill-down."
                onClose={() => setDrillOpen(false)}
                className="max-w-4xl"
            >
                {drillLoading ? (
                    <p className="text-sm text-slate-400">Loading reviews...</p>
                ) : !drillRows?.length ? (
                    <p className="text-sm text-slate-400">No reviews found for this selection.</p>
                ) : (
                    <div className="space-y-3">
                        <div className="flex justify-end">
                            <button
                                type="button"
                                onClick={() => {
                                    const rows = (drillRows || []).map((row) => ({
                                        date: row.date,
                                        product: row.product_name || row.product,
                                        source: row.source,
                                        rating: row.rating,
                                        sentiment: row.sentiment_label,
                                        text: row.review_text,
                                    }))
                                    downloadTextFile(
                                        toCsv(rows),
                                        `dashboard_drilldown_${(brand || 'all')}_${rangeDays}d.csv`,
                                        'text/csv;charset=utf-8',
                                    )
                                    toast.success('Downloaded drill-down CSV.')
                                }}
                                className={cn(
                                    'rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs font-semibold text-slate-200 transition',
                                    'hover:bg-white/[0.06] hover:text-white',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                            >
                                Download CSV
                            </button>
                        </div>

                        <div className="overflow-hidden rounded-2xl border border-white/10">
                            {(drillRows || []).map((row) => (
                                <div key={row.review_id} className="border-t border-white/10 bg-white/[0.02] px-4 py-3 first:border-t-0">
                                    <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
                                        <span>
                                            {row.date} | {row.product_name || row.product} | {row.source}
                                        </span>
                                        <span className="font-semibold text-slate-200">
                                            {row.sentiment_label} | {Math.round(((Number(row.sentiment_score) || 0) + 1) * 50)}%
                                        </span>
                                    </div>
                                    <p className="mt-2 text-sm text-slate-200">{row.review_text}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </Modal>
        </div>
    )
}
