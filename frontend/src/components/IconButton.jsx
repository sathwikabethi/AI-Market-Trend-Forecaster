import { cn } from '../lib/cn'

export default function IconButton({ children, label, className, ...props }) {
    return (
        <button
            type="button"
            aria-label={label}
            className={cn(
                'inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-slate-200 shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur transition',
                'hover:bg-white/[0.06] hover:text-white',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                className,
            )}
            {...props}
        >
            {children}
        </button>
    )
}

