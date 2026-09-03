import { cn } from '../lib/cn'

export default function Skeleton({ className = '' }) {
    return (
        <div
            aria-hidden="true"
            className={cn(
                'animate-pulse rounded-2xl bg-white/[0.06] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]',
                className,
            )}
        />
    )
}

