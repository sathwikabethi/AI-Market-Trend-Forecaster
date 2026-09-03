import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts'
import { cn } from '../lib/cn'

function DonutCenter({ value, label }) {
    return (
        <div className="absolute inset-0 flex flex-col items-center justify-center">
            <p className="text-2xl font-semibold tracking-tight text-white">{value}</p>
            <p className="text-xs text-slate-400">{label}</p>
        </div>
    )
}

export default function SentimentCard({ sentiment, onViewAll }) {
    const items = Array.isArray(sentiment?.items) ? sentiment.items : []
    const centerValue = sentiment?.centerValue ?? sentiment?.center_value ?? '0%'
    const centerLabel = sentiment?.centerLabel ?? sentiment?.center_label ?? ''
    const data = items.map((item) => ({
        name: item.label,
        value: Number(item.value) || 0,
        color: item.color,
    }))

    return (
        <section className="rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-white/[0.03] p-5 shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur">
            <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-white">Sentiment Distribution</h3>
                <button
                    type="button"
                    onClick={onViewAll}
                    className={cn(
                        'text-xs font-medium text-violet-300/90 transition hover:text-violet-200',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                    )}
                >
                    View All &gt;
                </button>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-[180px_1fr] sm:items-center">
                <div className="relative h-[180px]">
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={data}
                                dataKey="value"
                                innerRadius="62%"
                                outerRadius="82%"
                                paddingAngle={3}
                                cornerRadius={10}
                                stroke="rgba(0,0,0,0.35)"
                                startAngle={90}
                                endAngle={450}
                            >
                                {data.map((entry) => (
                                    <Cell key={entry.name} fill={entry.color} />
                                ))}
                            </Pie>
                        </PieChart>
                    </ResponsiveContainer>
                    <DonutCenter value={centerValue} label={centerLabel} />
                </div>

                <div className="space-y-3">
                    {items.map((item) => (
                        <div key={item.label} className="flex items-center justify-between gap-3 text-xs">
                            <div className="flex items-center gap-2 text-slate-300">
                                <span className="h-2 w-2 rounded-full" style={{ background: item.color }} />
                                <span>{item.label}</span>
                            </div>
                            <span className="font-semibold text-white">{item.value}%</span>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    )
}
