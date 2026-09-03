import axios from 'axios'

// Legacy keys from the previous bearer-token-in-localStorage approach. We keep
// a cleanup helper so users don't carry old tokens forever.
const LEGACY_TOKEN_KEY = 'market_access_token'
const LEGACY_REFRESH_TOKEN_KEY = 'market_refresh_token'

const rawBaseURL = import.meta.env.VITE_API_BASE_URL || '/api'
const baseURL = rawBaseURL.endsWith('/') ? rawBaseURL.slice(0, -1) : rawBaseURL

const api = axios.create({
    baseURL,
    timeout: 20000,
    withCredentials: true,
})

const refreshClient = axios.create({
    baseURL,
    timeout: 20000,
    withCredentials: true,
})

export function clearLegacyTokens() {
    localStorage.removeItem(LEGACY_TOKEN_KEY)
    localStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY)
}

async function performRefresh() {
    const response = await refreshClient.post('/auth/refresh', {})
    return response.data
}

let _refreshPromise = null

api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const status = error?.response?.status
        const original = error?.config
        const url = String(original?.url || '')
        const isAuthCall = url.includes('/auth/login') || url.includes('/auth/register') || url.includes('/auth/refresh')
        if (status !== 401 || !original || original.__isRetryRequest || isAuthCall) {
            return Promise.reject(error)
        }

        original.__isRetryRequest = true
        try {
            _refreshPromise = _refreshPromise || performRefresh().finally(() => {
                _refreshPromise = null
            })
            await _refreshPromise
            return api(original)
        } catch (refreshErr) {
            return Promise.reject(refreshErr)
        }
    },
)

export async function registerUser({ name, email, password }) {
    const response = await api.post('/auth/register', { name, email, password })
    return response.data
}

export async function loginUser({ email, password, mfa_code }) {
    const body = { email, password }
    if ((mfa_code || '').trim()) {
        body.mfa_code = mfa_code
    }
    const response = await api.post('/auth/login', body)
    return response.data
}

export async function logoutUser() {
    const response = await api.post('/auth/logout')
    return response.data
}

export async function getCurrentUser() {
    const response = await api.get('/auth/me')
    return response.data
}

export async function analyzeReview(text, product = 'general') {
    const response = await api.post('/analyze', { text, product })
    return response.data
}

export async function submitAnalyzeJob(text, product = 'general') {
    const response = await api.post('/jobs/analyze', { text, product })
    return response.data
}

export async function getAnalyzeJob(jobId) {
    const response = await api.get(`/jobs/${jobId}`)
    return response.data
}

export async function getProducts() {
    const response = await api.get('/products')
    return response.data
}

export async function getProductTrends(productId) {
    const response = await api.get('/trends', {
        params: { product: productId },
    })
    return response.data
}

export async function getDataStatus() {
    const response = await api.get('/data/status')
    return response.data
}

export async function getDataVersions(limit = 20) {
    const response = await api.get('/data/versions', {
        params: { limit },
    })
    return response.data
}

export async function getPreprocessingAudits(limit = 20) {
    const response = await api.get('/data/preprocessing-audits', {
        params: { limit },
    })
    return response.data
}

export async function getAdminOverview() {
    const response = await api.get('/admin/overview')
    return response.data
}

export async function triggerIngestion(source = 'manual', batchSize = 4) {
    const response = await api.post('/ingestion/run', {
        source,
        batch_size: batchSize,
    })
    return response.data
}

export async function getIngestionRuns(limit = 50) {
    const response = await api.get('/ingestion/runs', {
        params: { limit },
    })
    return response.data
}

export async function getAdminAlerts(limit = 50) {
    const response = await api.get('/admin/alerts', {
        params: { limit },
    })
    return response.data
}

export async function getMetrics() {
    const response = await api.get('/metrics')
    return response.data
}

export async function getQueueStatus() {
    const response = await api.get('/queue/status')
    return response.data
}

export async function getRagStatus() {
    const response = await api.get('/rag/status')
    return response.data
}

export async function askRag(question, product = null, topK = 5) {
    const response = await api.post('/rag/ask', {
        question,
        product,
        top_k: topK,
    })
    return response.data
}

export async function getDashboardOverview(product = null, days = 7, options = {}) {
    const params = { days }
    if (product && product !== 'all') {
        params.product = product
    }
    if (options?.topic) {
        params.topic = options.topic
    }
    if (options?.sourceMix && typeof options.sourceMix === 'object') {
        const entries = Object.entries(options.sourceMix)
            .filter(([k, v]) => k && Number.isFinite(Number(v)))
            .map(([k, v]) => `${k}:${Math.round(Number(v))}`)
        if (entries.length) {
            params.source_mix = entries.join(',')
        }
    }
    if (options?.refresh) {
        params.refresh = true
    }
    const response = await api.get('/dashboard/overview', { params })
    return response.data
}

export async function getDashboardReviews(options = {}) {
    const params = {
        days: options?.days ?? 7,
        limit: options?.limit ?? 60,
    }
    const product = options?.product
    if (product && product !== 'all') {
        params.product = product
    }
    if (options?.topic) params.topic = options.topic
    if (options?.source) params.source = options.source
    if (options?.region) params.region = options.region

    const response = await api.get('/dashboard/reviews', { params })
    return response.data
}

export async function updateProfile({ name }) {
    const response = await api.patch('/auth/profile', { name })
    return response.data
}

export async function changePassword({ current_password, new_password }) {
    const response = await api.post('/auth/password/change', { current_password, new_password })
    return response.data
}

export async function getMfaStatus() {
    const response = await api.get('/auth/mfa/status')
    return response.data
}

export async function setupMfa() {
    const response = await api.post('/auth/mfa/setup', {})
    return response.data
}

export async function enableMfa(code) {
    const response = await api.post('/auth/mfa/enable', { code })
    return response.data
}

export async function disableMfa(password) {
    const response = await api.post('/auth/mfa/disable', { password })
    return response.data
}

export async function listSessions() {
    const response = await api.get('/auth/sessions')
    return response.data
}

export async function revokeSession(session_id) {
    const response = await api.post('/auth/sessions/revoke', { session_id })
    return response.data
}

export async function revokeAllSessions() {
    const response = await api.post('/auth/sessions/revoke-all', {})
    return response.data
}

export async function listApiKeys() {
    const response = await api.get('/auth/api-keys')
    return response.data
}

export async function createApiKey(name = null) {
    const body = {}
    if ((name || '').trim()) body.name = name
    const response = await api.post('/auth/api-keys', body)
    return response.data
}

export async function revokeApiKey(key_id) {
    const response = await api.post('/auth/api-keys/revoke', { key_id })
    return response.data
}

export function getApiBaseURL() {
    return baseURL
}

export function getExportUrl(kind = 'processed') {
    const safeKind = kind === 'raw' ? 'raw' : 'processed'
    return `${baseURL}/export/${safeKind}`
}
