import {
    CartesianGrid,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts'

export default function TrendChart({ data, height = 320 }) {
    if (!data.length) {
        return <p className="text-sm text-slate-500 dark:text-slate-400">No trend data returned.</p>
    }

    return (
        <div className="w-full" style={{ height }}>
            <ResponsiveContainer>
                <LineChart
                    data={data}
                    margin={{ top: 10, right: 10, left: -10, bottom: 0 }}
                >
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.25} />
                    <XAxis dataKey="month" tick={{ fontSize: 12, fill: '#94a3b8' }} />
                    <YAxis yAxisId="left" tick={{ fontSize: 12, fill: '#94a3b8' }} />
                    <YAxis
                        yAxisId="right"
                        orientation="right"
                        tick={{ fontSize: 12, fill: '#94a3b8' }}
                    />
                    <Tooltip
                        contentStyle={{
                            background: '#0f172a',
                            border: '1px solid #1e293b',
                            borderRadius: '0.75rem',
                            color: '#e2e8f0',
                        }}
                    />
                    <Line
                        yAxisId="left"
                        type="monotone"
                        dataKey="sentiment_score"
                        stroke="#8b5cf6"
                        strokeWidth={2}
                        dot={false}
                        name="Sentiment"
                    />
                    <Line
                        yAxisId="right"
                        type="monotone"
                        dataKey="volume"
                        stroke="#f59e0b"
                        strokeWidth={2}
                        dot={false}
                        name="Volume"
                    />
                </LineChart>
            </ResponsiveContainer>
        </div>
    )
}
