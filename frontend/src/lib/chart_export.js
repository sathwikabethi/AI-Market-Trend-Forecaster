import { downloadTextFile } from './download'

function getFirstSvg(root) {
    if (!root) return null
    if (root instanceof SVGSVGElement) return root
    return root.querySelector?.('svg') || null
}

function serializeSvg(svg) {
    const clone = svg.cloneNode(true)
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')

    const rect = svg.getBoundingClientRect()
    const width = Math.max(1, Math.ceil(rect.width))
    const height = Math.max(1, Math.ceil(rect.height))

    clone.setAttribute('width', String(width))
    clone.setAttribute('height', String(height))
    if (!clone.getAttribute('viewBox')) {
        clone.setAttribute('viewBox', `0 0 ${width} ${height}`)
    }

    const svgString = new XMLSerializer().serializeToString(clone)
    return { svgString, width, height }
}

async function svgToPngDataUrl(svgString, width, height, scale = 2) {
    const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
    const url = URL.createObjectURL(blob)

    try {
        const image = new Image()
        const loaded = new Promise((resolve, reject) => {
            image.onload = resolve
            image.onerror = reject
        })
        image.src = url
        await loaded

        const canvas = document.createElement('canvas')
        canvas.width = Math.max(1, Math.floor(width * scale))
        canvas.height = Math.max(1, Math.floor(height * scale))
        const ctx = canvas.getContext('2d')
        if (!ctx) {
            throw new Error('Canvas not supported')
        }

        // Match the dashboard card background so the PNG looks consistent.
        ctx.fillStyle = '#0b0d14'
        ctx.fillRect(0, 0, canvas.width, canvas.height)
        ctx.scale(scale, scale)
        ctx.drawImage(image, 0, 0, width, height)

        return canvas.toDataURL('image/png')
    } finally {
        URL.revokeObjectURL(url)
    }
}

export async function exportChartAsPng(rootElement, filename = 'chart.png') {
    const svg = getFirstSvg(rootElement)
    if (!svg) throw new Error('No SVG chart found')
    const { svgString, width, height } = serializeSvg(svg)
    const dataUrl = await svgToPngDataUrl(svgString, width, height)

    const base64 = dataUrl.split(',')[1] || ''
    const binary = atob(base64)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
    const blob = new Blob([bytes], { type: 'image/png' })
    const url = URL.createObjectURL(blob)

    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()

    window.setTimeout(() => URL.revokeObjectURL(url), 2500)
}

export async function openPrintPdfWindow({ title, subtitle, rootElement, meta }) {
    const svg = getFirstSvg(rootElement)
    if (!svg) throw new Error('No SVG chart found')
    const { svgString, width, height } = serializeSvg(svg)
    const dataUrl = await svgToPngDataUrl(svgString, width, height, 2)

    const win = window.open('', '_blank', 'noopener,noreferrer')
    if (!win) throw new Error('Popup blocked')

    const safeTitle = String(title || 'Dashboard Report')
    const safeSubtitle = String(subtitle || '')
    const safeMeta = String(meta || '').trim()

    win.document.write(`<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${safeTitle}</title>
  <style>
    :root { color-scheme: dark; }
    body { margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; background: #0b0d14; color: #e2e8f0; }
    .wrap { padding: 28px; }
    h1 { font-size: 18px; margin: 0; color: #ffffff; }
    p { margin: 8px 0 0; font-size: 12px; color: rgba(148,163,184,0.95); }
    img { width: 100%; max-width: 920px; height: auto; margin-top: 18px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.10); }
    .meta { margin-top: 12px; font-size: 11px; color: rgba(148,163,184,0.85); }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>${safeTitle}</h1>
    <p>${safeSubtitle}</p>
    <img src="${dataUrl}" alt="Chart" width="${Math.max(1, Math.floor(width * 2))}" height="${Math.max(1, Math.floor(height * 2))}" />
    ${safeMeta ? `<div class="meta">${safeMeta}</div>` : ''}
  </div>
</body>
</html>`)
    win.document.close()
    win.focus()
    win.print()
}

export function exportChartAsSvg(rootElement, filename = 'chart.svg') {
    const svg = getFirstSvg(rootElement)
    if (!svg) throw new Error('No SVG chart found')
    const { svgString } = serializeSvg(svg)
    downloadTextFile(svgString, filename, 'image/svg+xml;charset=utf-8')
}

