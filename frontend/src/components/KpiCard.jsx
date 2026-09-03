import ProgressRing from './ProgressRing'

export default function KpiCard({ helper, label, value, progress, accent = '#22d3ee' }) {
    return (
        <article className="rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-white/[0.03] p-5 shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-slate-400">
                        {helper}
                    </p>
                    <p className="mt-2 text-sm text-slate-200">{label}</p>
                    <p className="mt-2 text-3xl font-semibold tracking-tight text-white">{value}</p>
                </div>
                <ProgressRing value={progress} color={accent} />
            </div>
        </article>
    )
}

