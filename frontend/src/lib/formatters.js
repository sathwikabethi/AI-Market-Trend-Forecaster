export function formatScore(value, digits = 3) {
    const n = Number(value)
    return Number.isFinite(n) ? n.toFixed(digits) : Number(0).toFixed(digits)
}

export function normalizeProducts(value) {
    if (!Array.isArray(value)) {
        return []
    }
    return value
        .map((item) => {
            if (!item || typeof item !== 'object') {
                return null
            }
            return {
                id: String(item.id ?? ''),
                name: String(item.name ?? ''),
            }
        })
        .filter((item) => item && item.id && item.name)
}

export function normalizeTrendRows(value) {
    if (!Array.isArray(value)) {
        return []
    }
    return value
        .map((item) => {
            if (!item || typeof item !== 'object') {
                return null
            }
            return {
                date: String(item.date ?? ''),
                sentiment_score: Number(item.sentiment_score ?? 0),
                volume: Number(item.volume ?? 0),
            }
        })
        .filter((item) => item && item.date)
}

export function withMonthLabel(rows) {
    return rows.map((item) => ({
        ...item,
        month: item.date.slice(0, 7),
    }))
}

export function summarizeTrendRows(rows) {
    if (!rows.length) {
        return {
            avgSentiment: 0,
            totalVolume: 0,
            momentum: 0,
            peakMonth: '-',
        }
    }

    const totalSentiment = rows.reduce((sum, item) => sum + item.sentiment_score, 0)
    const totalVolume = rows.reduce((sum, item) => sum + item.volume, 0)
    const first = rows[0]
    const last = rows[rows.length - 1]
    const peak = rows.reduce(
        (current, item) => (item.volume > current.volume ? item : current),
        rows[0],
    )

    return {
        avgSentiment: totalSentiment / rows.length,
        totalVolume,
        momentum: last.sentiment_score - first.sentiment_score,
        peakMonth: peak.date.slice(0, 7),
    }
}
