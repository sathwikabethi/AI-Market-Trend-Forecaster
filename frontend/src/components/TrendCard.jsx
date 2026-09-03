import {
    Area,
    AreaChart,
    CartesianGrid,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts'
import { cn } from '../lib/cn'

function buildMultiSeries(lines) {
    if (!Array.isArray(lines) || !lines.length) return []
    const byKey = new Map()
    for (const line of lines) {
        if (!line?.key) continue
        byKey.set(line.key, line.data || [])
    }

    const firstKey = lines[0]?.key
    const base = (byKey.get(firstKey) || []).map((row) => ({ day: row.day }))
    return base.map((row, index) => {
        const next = { ...row }
        for (const line of lines) {
            const point = byKey.get(line.key)?.[index]
            next[line.key] = point?.value ?? 0
        }
        return next
    })
}

function ChartTooltip({ active, payload, label, mode, lines }) {
    if (!active || !payload?.length) return null
    const entries = payload
        .filter((item) => item && item.dataKey && typeof item.value === 'number')
        .map((item) => ({
            key: item.dataKey,
            value: item.value,
            color: item.color,
        }))

    return (
        <div className="rounded-xl border border-white/10 bg-[#0b0d14]/90 px-3 py-2 shadow-[0_20px_60px_rgba(0,0,0,0.65)] backdrop-blur">
            <p className="text-xs font-semibold text-slate-200">{label}</p>
            <div className="mt-2 space-y-1">
                {mode === 'multi' ? entries.map((item) => {
                    const labelText = lines.find((l) => l.key === item.key)?.label || item.key
                    return (
                        <div key={item.key} className="flex items-center justify-between gap-4 text-xs">
                            <div className="flex items-center gap-2 text-slate-300">
                                <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
                                <span>{labelText}</span>
                            </div>
                            <span className="font-semibold text-white">{Math.round(item.value)}</span>
                        </div>
                    )
                }) : (
                    <div className="flex items-center justify-between gap-4 text-xs">
                        <span className="text-slate-300">Sentiment</span>
                        <span className="font-semibold text-white">{Math.round(entries[0]?.value ?? 0)}</span>
                    </div>
                )}
            </div>
        </div>
    )
}

export default function TrendCard({ title, subtitle, trend }) {
    const mode = trend?.mode === 'multi' ? 'multi' : 'single'
    const lines = mode === 'multi' ? (trend?.lines || []) : []
    const data = mode === 'multi' ? buildMultiSeries(lines) : (trend?.line?.data || [])
    const singleColor = trend?.line?.color || '#22d3ee'

    return (
        <section className="relative overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-white/[0.03] p-5 shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur">
            <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                <div>
                    <h3 className="text-base font-semibold text-white">{title}</h3>
                    <p className="mt-1 text-xs text-slate-400">{subtitle}</p>
                </div>
                {mode === 'multi' ? (
                    <div className="flex flex-wrap items-center gap-4 text-xs text-slate-300">
                        {lines.map((line) => (
                            <div key={line.key} className="flex items-center gap-2">
                                <span className="h-2 w-2 rounded-full" style={{ background: line.color }} />
                                <span>{line.label}</span>
                            </div>
                        ))}
                    </div>
                ) : null}
            </div>

            <div
                className={cn(
                    'relative mt-5 h-[320px] overflow-hidden rounded-2xl border border-white/5 bg-black/20',
                    'shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]',
                )}
            >
                <div
                    className="pointer-events-none absolute inset-0"
                    style={{
                        background:
                            mode === 'single'
                                ? `radial-gradient(650px circle at 35% 40%, ${singleColor}26, transparent 60%)`
                                : 'radial-gradient(650px circle at 35% 40%, rgba(34,211,238,0.10), transparent 60%)',
                    }}
                />
                <ResponsiveContainer width="100%" height="100%">
                    {mode === 'multi' ? (
                        <LineChart data={data} margin={{ top: 16, right: 18, left: 6, bottom: 8 }}>
                            <CartesianGrid stroke="rgba(255,255,255,0.06)" strokeDasharray="3 6" />
                            <XAxis
                                dataKey="day"
                                tick={{ fontSize: 12, fill: 'rgba(148,163,184,0.85)' }}
                                axisLine={false}
                                tickLine={false}
                            />
                            <YAxis
                                domain={[40, 100]}
                                tick={{ fontSize: 12, fill: 'rgba(148,163,184,0.85)' }}
                                axisLine={false}
                                tickLine={false}
                            />
                            <Tooltip
                                cursor={{ stroke: 'rgba(255,255,255,0.10)', strokeDasharray: '4 6' }}
                                content={(props) => (
                                    <ChartTooltip {...props} mode="multi" lines={lines} />
                                )}
                            />
                            {lines.map((line) => (
                                <Line
                                    key={line.key}
                                    type="monotone"
                                    dataKey={line.key}
                                    stroke={line.color}
                                    strokeWidth={2.25}
                                    dot={false}
                                    activeDot={{ r: 4, strokeWidth: 0 }}
                                />
                            ))}
                        </LineChart>
                    ) : (
                        <AreaChart data={data} margin={{ top: 18, right: 18, left: 6, bottom: 8 }}>
                            <defs>
                                <linearGradient id="singleFill" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor={singleColor} stopOpacity={0.35} />
                                    <stop offset="100%" stopColor={singleColor} stopOpacity={0.02} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid stroke="rgba(255,255,255,0.06)" strokeDasharray="3 6" />
                            <XAxis
                                dataKey="day"
                                tick={{ fontSize: 12, fill: 'rgba(148,163,184,0.85)' }}
                                axisLine={false}
                                tickLine={false}
                            />
                            <YAxis
                                domain={[40, 100]}
                                tick={{ fontSize: 12, fill: 'rgba(148,163,184,0.85)' }}
                                axisLine={false}
                                tickLine={false}
                            />
                            <Tooltip
                                cursor={{ stroke: 'rgba(255,255,255,0.10)', strokeDasharray: '4 6' }}
                                content={(props) => (
                                    <ChartTooltip {...props} mode="single" lines={[]} />
                                )}
                            />
                            <Area
                                type="monotone"
                                dataKey="value"
                                stroke={singleColor}
                                strokeWidth={2.5}
                                fill="url(#singleFill)"
                                dot={false}
                                activeDot={{ r: 4, strokeWidth: 0 }}
                            />
                        </AreaChart>
                    )}
                </ResponsiveContainer>
            </div>
        </section>
    )
}

