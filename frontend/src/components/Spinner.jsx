import { cn } from '../lib/cn'

export default function Spinner({ label = 'Loading...', size = 18, className = '' }) {
    const px = Math.max(12, Number(size) || 18)

    return (
        <div className={cn('inline-flex items-center gap-3', className)} role="status" aria-live="polite">
            <span
                aria-hidden="true"
                className="relative inline-grid place-items-center"
                style={{ width: px, height: px }}
            >
                <span className="absolute inset-0 rounded-full border-2 border-white/10" />
                <span className="absolute inset-0 animate-spin rounded-full border-2 border-cyan-300 border-t-transparent" />
            </span>
            {label ? <span className="text-xs font-medium text-slate-300">{label}</span> : null}
        </div>
    )
}
