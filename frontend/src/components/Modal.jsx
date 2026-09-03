import { useEffect } from 'react'
import { X } from 'lucide-react'
import { cn } from '../lib/cn'

export default function Modal({ open, title, description, onClose, children, className }) {
    useEffect(() => {
        if (!open) return undefined
        const handler = (event) => {
            if (event.key === 'Escape') onClose?.()
        }
        document.addEventListener('keydown', handler)
        return () => document.removeEventListener('keydown', handler)
    }, [open, onClose])

    if (!open) return null

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4 py-8" role="dialog" aria-modal="true">
            <button
                type="button"
                aria-label="Close dialog"
                className="absolute inset-0 bg-black/60 backdrop-blur-[2px]"
                onClick={onClose}
            />

            <div
                className={cn(
                    'relative w-full max-w-lg overflow-hidden rounded-2xl border border-white/10 bg-[#0b0d14]/90 shadow-[0_20px_60px_rgba(0,0,0,0.65)] backdrop-blur',
                    className,
                )}
            >
                <div className="flex items-start justify-between gap-4 border-b border-white/10 px-6 py-4">
                    <div>
                        <h2 className="text-sm font-semibold text-white">{title}</h2>
                        {description ? <p className="mt-1 text-xs text-slate-400">{description}</p> : null}
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        className={cn(
                            'inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-slate-200 transition',
                            'hover:bg-white/[0.06] hover:text-white',
                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                        )}
                        aria-label="Close"
                    >
                        <X size={16} className="opacity-90" />
                    </button>
                </div>

                <div className="px-6 py-5">
                    {children}
                </div>
            </div>
        </div>
    )
}

