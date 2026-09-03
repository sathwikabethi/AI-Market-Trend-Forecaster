export function downloadTextFile(text, filename, mime = 'text/plain;charset=utf-8') {
    const blob = new Blob([text], { type: mime })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()

    window.setTimeout(() => {
        URL.revokeObjectURL(url)
    }, 2500)
}

function escapeCsvValue(value) {
    const raw = value == null ? '' : String(value)
    if (raw.includes('"') || raw.includes(',') || raw.includes('\n') || raw.includes('\r')) {
        return `"${raw.replaceAll('"', '""')}"`
    }
    return raw
}

export function toCsv(rows) {
    const data = Array.isArray(rows) ? rows : []
    if (!data.length) return ''

    const headers = Array.from(
        data.reduce((acc, row) => {
            for (const key of Object.keys(row || {})) acc.add(key)
            return acc
        }, new Set()),
    )

    const lines = [
        headers.map(escapeCsvValue).join(','),
        ...data.map((row) => headers.map((h) => escapeCsvValue(row?.[h])).join(',')),
    ]

    return lines.join('\n')
}

