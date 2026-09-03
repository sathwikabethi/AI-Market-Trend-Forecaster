export default function ProgressRing({
    value = 0,
    size = 44,
    stroke = 5,
    color = '#22d3ee',
    label,
}) {
    const safe = Number.isFinite(Number(value)) ? Math.max(0, Math.min(100, Number(value))) : 0
    const radius = (size - stroke) / 2
    const circumference = 2 * Math.PI * radius
    const dash = (safe / 100) * circumference

    return (
        <div className="relative inline-flex" style={{ width: size, height: size }}>
            <svg width={size} height={size} className="rotate-[-90deg]">
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="transparent"
                    stroke="rgba(255,255,255,0.10)"
                    strokeWidth={stroke}
                />
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="transparent"
                    stroke={color}
                    strokeWidth={stroke}
                    strokeDasharray={`${dash} ${circumference - dash}`}
                    strokeLinecap="round"
                    style={{ filter: `drop-shadow(0 0 10px ${color}55)` }}
                />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-[11px] font-semibold text-slate-100">
                    {label ?? `${Math.round(safe)}%`}
                </span>
            </div>
        </div>
    )
}

