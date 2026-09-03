import { cn } from '../lib/cn'

export default function TrendingTopicsCard({ topics, selectedTopic, onToggleTopic }) {
    const items = Array.isArray(topics) ? topics : []
    const activeKey = (selectedTopic || '').trim().toLowerCase()

    return (
        <section className="mt-6 rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-white/[0.03] p-6 shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur">
            <p className="text-[11px] font-semibold uppercase tracking-[0.32em] text-slate-400">
                Trending Topics
            </p>

            <div className="mt-4 flex flex-wrap gap-2">
                {items.map((topic) => (
                    <button
                        type="button"
                        key={topic.label}
                        onClick={() => onToggleTopic?.(topic)}
                        className={cn(
                            'inline-flex items-center rounded-full border px-4 py-2 text-xs font-medium transition',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                            activeKey && String(topic.label || '').toLowerCase() === activeKey
                                ? 'border-cyan-400/35 bg-cyan-400/10 text-cyan-200 shadow-[0_0_18px_rgba(34,211,238,0.12)]'
                                : topic.highlighted
                                    ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300 shadow-[0_0_16px_rgba(34,197,94,0.10)]'
                                    : 'border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.06] hover:text-white',
                        )}
                    >
                        {topic.label}
                    </button>
                ))}
            </div>
        </section>
    )
}
