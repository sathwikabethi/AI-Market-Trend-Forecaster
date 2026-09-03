import { Copy, ExternalLink, RefreshCcw, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import Modal from '../components/Modal'
import TopNav from '../components/TopNav'
import Spinner from '../components/Spinner'
import { cn } from '../lib/cn'
import {
    changePassword,
    createApiKey,
    disableMfa,
    enableMfa,
    getApiBaseURL,
    getDataStatus,
    getExportUrl,
    getMetrics,
    getMfaStatus,
    listApiKeys,
    listSessions,
    revokeApiKey,
    revokeAllSessions,
    revokeSession,
    setupMfa,
    updateProfile,
} from '../lib/api'

const NOTIFY_KEY = 'tf_notification_prefs'

function loadNotifyPrefs() {
    try {
        const raw = localStorage.getItem(NOTIFY_KEY)
        const parsed = raw ? JSON.parse(raw) : {}
        return typeof parsed === 'object' && parsed ? parsed : {}
    } catch {
        return {}
    }
}

function SectionCard({ title, description, children }) {
    return (
        <section className="rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-white/[0.03] p-6 shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur">
            <h2 className="text-sm font-semibold text-white">{title}</h2>
            {description ? <p className="mt-2 text-sm text-slate-400">{description}</p> : null}
            <div className="mt-4">{children}</div>
        </section>
    )
}

function ToggleRow({ label, checked, onChange }) {
    return (
        <label className="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
            <span className="text-sm font-semibold text-slate-200">{label}</span>
            <input type="checkbox" checked={checked} onChange={(e) => onChange?.(e.target.checked)} />
        </label>
    )
}

export default function SettingsPage({ user, theme, onToggleTheme, onLogout, onUserUpdate }) {
    const isAdmin = String(user?.role || '').toLowerCase() === 'admin'

    const [name, setName] = useState(user?.name || '')
    const [profileSaving, setProfileSaving] = useState(false)

    const [currentPassword, setCurrentPassword] = useState('')
    const [newPassword, setNewPassword] = useState('')
    const [passwordSaving, setPasswordSaving] = useState(false)

    const [mfaStatus, setMfaStatus] = useState({ enabled: false })
    const [mfaBusy, setMfaBusy] = useState(false)
    const [mfaSetupOpen, setMfaSetupOpen] = useState(false)
    const [mfaSetupPayload, setMfaSetupPayload] = useState(null)
    const [mfaCode, setMfaCode] = useState('')
    const [mfaDisablePassword, setMfaDisablePassword] = useState('')

    const [sessions, setSessions] = useState([])
    const [sessionsBusy, setSessionsBusy] = useState(false)

    const [apiKeys, setApiKeys] = useState([])
    const [apiKeysBusy, setApiKeysBusy] = useState(false)
    const [apiKeyName, setApiKeyName] = useState('')
    const [createdKey, setCreatedKey] = useState(null)
    const [createdKeyOpen, setCreatedKeyOpen] = useState(false)

    const [notifyPrefs, setNotifyPrefs] = useState(() => {
        const prefs = loadNotifyPrefs()
        return {
            anomalyAlerts: prefs.anomalyAlerts ?? true,
            securityToasts: prefs.securityToasts ?? true,
        }
    })

    const [metrics, setMetrics] = useState(null)
    const [dataStatus, setDataStatus] = useState(null)
    const [envBusy, setEnvBusy] = useState(false)

    useEffect(() => {
        setName(user?.name || '')
    }, [user?.name])

    useEffect(() => {
        localStorage.setItem(NOTIFY_KEY, JSON.stringify(notifyPrefs))
    }, [notifyPrefs])

    const refreshMfa = async () => {
        try {
            const status = await getMfaStatus()
            setMfaStatus(status || { enabled: false })
        } catch (err) {
            toast.error(err?.response?.data?.message || err?.response?.data?.detail || 'Failed to load MFA status.')
        }
    }

    const refreshSessions = async () => {
        setSessionsBusy(true)
        try {
            const rows = await listSessions()
            setSessions(Array.isArray(rows) ? rows : [])
        } catch (err) {
            toast.error(err?.response?.data?.message || err?.response?.data?.detail || 'Failed to load sessions.')
        } finally {
            setSessionsBusy(false)
        }
    }

    const refreshApiKeys = async () => {
        setApiKeysBusy(true)
        try {
            const rows = await listApiKeys()
            setApiKeys(Array.isArray(rows) ? rows : [])
        } catch (err) {
            toast.error(err?.response?.data?.message || err?.response?.data?.detail || 'Failed to load API keys.')
        } finally {
            setApiKeysBusy(false)
        }
    }

    const refreshEnv = async () => {
        setEnvBusy(true)
        try {
            const [m, d] = await Promise.all([getMetrics(), getDataStatus()])
            setMetrics(m)
            setDataStatus(d)
        } catch (err) {
            toast.error(err?.response?.data?.message || err?.response?.data?.detail || 'Failed to load environment status.')
        } finally {
            setEnvBusy(false)
        }
    }

    useEffect(() => {
        refreshMfa()
        refreshSessions()
        refreshApiKeys()
        refreshEnv()
    }, [])

    const sessionSummary = useMemo(() => {
        const rows = Array.isArray(sessions) ? sessions : []
        return {
            total: rows.length,
            active: rows.filter((s) => !s.revoked_at).length,
        }
    }, [sessions])

    return (
        <div className="min-h-screen bg-tf-bg text-tf-fg">
            <TopNav user={user} theme={theme} onToggleTheme={onToggleTheme} onLogout={onLogout} />

            <main className="mx-auto w-full max-w-6xl px-4 pb-12 pt-8">
                <h1 className="text-3xl font-semibold tracking-tight text-white">Settings</h1>
                <p className="mt-2 text-sm text-slate-400">Profile, security, and environment info.</p>

                <section className="mt-6 grid gap-6 md:grid-cols-2">
                    <SectionCard title="Appearance" description="Toggle between light and dark themes.">
                        <button
                            type="button"
                            onClick={onToggleTheme}
                            className={cn(
                                'inline-flex items-center justify-center rounded-2xl px-4 py-3 text-sm font-semibold transition',
                                'border border-white/10 bg-white/[0.04] text-slate-200 hover:bg-white/[0.06] hover:text-white',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                            )}
                        >
                            Current: {theme}
                        </button>
                    </SectionCard>

                    <SectionCard title="Profile" description="Update your display name for this account.">
                        <div className="space-y-3">
                            <div>
                                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Email</p>
                                <p className="mt-2 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm font-semibold text-slate-200">
                                    {user?.email || 'user'}
                                </p>
                            </div>

                            <div>
                                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Name</p>
                                <input
                                    value={name}
                                    onChange={(e) => setName(e.target.value)}
                                    className={cn(
                                        'mt-2 w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-semibold text-slate-200',
                                        'shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] transition hover:bg-white/[0.06] hover:text-white',
                                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                    )}
                                    placeholder="Your name"
                                />
                            </div>

                            <button
                                type="button"
                                disabled={profileSaving || !name.trim() || name.trim() === (user?.name || '').trim()}
                                onClick={async () => {
                                    setProfileSaving(true)
                                    try {
                                        const updated = await updateProfile({ name: name.trim() })
                                        onUserUpdate?.(updated)
                                        toast.success('Profile updated.')
                                    } catch (err) {
                                        toast.error(err?.response?.data?.message || err?.response?.data?.detail || 'Profile update failed.')
                                    } finally {
                                        setProfileSaving(false)
                                    }
                                }}
                                className={cn(
                                    'inline-flex items-center justify-center rounded-2xl px-4 py-3 text-sm font-semibold transition',
                                    'bg-gradient-to-r from-cyan-400 to-sky-500 text-slate-950 shadow-[0_0_0_1px_rgba(34,211,238,0.30),0_18px_45px_rgba(34,211,238,0.16)]',
                                    'hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                            >
                                {profileSaving ? 'Saving...' : 'Save profile'}
                            </button>
                        </div>
                    </SectionCard>
                </section>

                <section className="mt-6 grid gap-6 lg:grid-cols-3">
                    <SectionCard title="Password" description="Rotate your password and revoke other sessions.">
                        <div className="space-y-3">
                            <input
                                value={currentPassword}
                                onChange={(e) => setCurrentPassword(e.target.value)}
                                type="password"
                                className={cn(
                                    'w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-semibold text-slate-200',
                                    'shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] transition hover:bg-white/[0.06] hover:text-white',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                                placeholder="Current password"
                            />
                            <input
                                value={newPassword}
                                onChange={(e) => setNewPassword(e.target.value)}
                                type="password"
                                className={cn(
                                    'w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-semibold text-slate-200',
                                    'shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] transition hover:bg-white/[0.06] hover:text-white',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                                placeholder="New password (min 10 chars)"
                            />
                            <button
                                type="button"
                                disabled={passwordSaving || !currentPassword || !newPassword}
                                onClick={async () => {
                                    setPasswordSaving(true)
                                    try {
                                        await changePassword({ current_password: currentPassword, new_password: newPassword })
                                        setCurrentPassword('')
                                        setNewPassword('')
                                        toast.success('Password changed.')
                                        refreshSessions()
                                    } catch (err) {
                                        toast.error(err?.response?.data?.message || err?.response?.data?.detail || 'Password change failed.')
                                    } finally {
                                        setPasswordSaving(false)
                                    }
                                }}
                                className={cn(
                                    'inline-flex items-center justify-center rounded-2xl px-4 py-3 text-sm font-semibold transition',
                                    'border border-white/10 bg-white/[0.04] text-slate-200 hover:bg-white/[0.06] hover:text-white',
                                    'disabled:cursor-not-allowed disabled:opacity-60',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                            >
                                {passwordSaving ? 'Updating...' : 'Change password'}
                            </button>
                        </div>
                    </SectionCard>

                    <SectionCard title="Multi-factor Auth" description="Enable MFA (TOTP) for extra security.">
                        <div className="space-y-3">
                            <p className="text-sm text-slate-200">
                                Status: <span className="font-semibold text-white">{mfaStatus?.enabled ? 'Enabled' : 'Disabled'}</span>
                            </p>

                            {!mfaStatus?.enabled ? (
                                <button
                                    type="button"
                                    disabled={mfaBusy}
                                    onClick={async () => {
                                        setMfaBusy(true)
                                        try {
                                            const payload = await setupMfa()
                                            setMfaSetupPayload(payload)
                                            setMfaCode('')
                                            setMfaSetupOpen(true)
                                        } catch (err) {
                                            toast.error(err?.response?.data?.message || err?.response?.data?.detail || 'MFA setup failed.')
                                        } finally {
                                            setMfaBusy(false)
                                        }
                                    }}
                                    className={cn(
                                        'inline-flex items-center justify-center rounded-2xl px-4 py-3 text-sm font-semibold transition',
                                        'bg-gradient-to-r from-cyan-400 to-sky-500 text-slate-950 shadow-[0_0_0_1px_rgba(34,211,238,0.30),0_18px_45px_rgba(34,211,238,0.16)]',
                                        'hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60',
                                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                    )}
                                >
                                    {mfaBusy ? 'Preparing...' : 'Set up MFA'}
                                </button>
                            ) : (
                                <>
                                    <input
                                        value={mfaDisablePassword}
                                        onChange={(e) => setMfaDisablePassword(e.target.value)}
                                        type="password"
                                        className={cn(
                                            'w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-semibold text-slate-200',
                                            'shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] transition hover:bg-white/[0.06] hover:text-white',
                                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                        )}
                                        placeholder="Password to disable MFA"
                                    />
                                    <button
                                        type="button"
                                        disabled={mfaBusy || !mfaDisablePassword}
                                        onClick={async () => {
                                            setMfaBusy(true)
                                            try {
                                                await disableMfa(mfaDisablePassword)
                                                setMfaDisablePassword('')
                                                toast.success('MFA disabled.')
                                                refreshMfa()
                                            } catch (err) {
                                                toast.error(err?.response?.data?.message || err?.response?.data?.detail || 'Failed to disable MFA.')
                                            } finally {
                                                setMfaBusy(false)
                                            }
                                        }}
                                        className={cn(
                                            'inline-flex items-center justify-center rounded-2xl px-4 py-3 text-sm font-semibold transition',
                                            'border border-white/10 bg-white/[0.04] text-slate-200 hover:bg-white/[0.06] hover:text-white',
                                            'disabled:cursor-not-allowed disabled:opacity-60',
                                            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                        )}
                                    >
                                        {mfaBusy ? 'Disabling...' : 'Disable MFA'}
                                    </button>
                                </>
                            )}
                        </div>
                    </SectionCard>

                    <SectionCard title="Notifications" description="Control in-app alerts and toasts.">
                        <div className="space-y-3">
                            <ToggleRow
                                label="Anomaly alerts"
                                checked={Boolean(notifyPrefs.anomalyAlerts)}
                                onChange={(checked) => setNotifyPrefs((p) => ({ ...p, anomalyAlerts: checked }))}
                            />
                            <ToggleRow
                                label="Security toasts"
                                checked={Boolean(notifyPrefs.securityToasts)}
                                onChange={(checked) => setNotifyPrefs((p) => ({ ...p, securityToasts: checked }))}
                            />
                        </div>
                    </SectionCard>
                </section>

                <section className="mt-6 grid gap-6 lg:grid-cols-3">
                    <SectionCard
                        title="Sessions"
                        description={`Manage sessions (${sessionSummary.active}/${sessionSummary.total} active).`}
                    >
                        <div className="space-y-3">
                            <div className="flex items-center justify-between gap-3">
                                <button
                                    type="button"
                                    disabled={sessionsBusy}
                                    onClick={refreshSessions}
                                    className={cn(
                                        'inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold text-slate-200 transition',
                                        'hover:bg-white/[0.06] hover:text-white',
                                        'disabled:cursor-not-allowed disabled:opacity-60',
                                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                    )}
                                >
                                    <RefreshCcw size={14} className={cn('opacity-80', sessionsBusy && 'animate-spin')} />
                                    Refresh
                                </button>
                                <button
                                    type="button"
                                    disabled={sessionsBusy}
                                    onClick={async () => {
                                        setSessionsBusy(true)
                                        try {
                                            await revokeAllSessions()
                                            toast.success('Revoked other sessions.')
                                            refreshSessions()
                                        } catch (err) {
                                            toast.error(err?.response?.data?.message || err?.response?.data?.detail || 'Failed to revoke sessions.')
                                        } finally {
                                            setSessionsBusy(false)
                                        }
                                    }}
                                    className={cn(
                                        'inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold text-slate-200 transition',
                                        'hover:bg-white/[0.06] hover:text-white',
                                        'disabled:cursor-not-allowed disabled:opacity-60',
                                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                    )}
                                >
                                    Revoke others
                                </button>
                            </div>

                            <div className="max-h-72 space-y-2 overflow-auto pr-1">
                                {(sessions || []).map((row) => (
                                    <div key={row.session_id} className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                                        <div className="flex items-center justify-between gap-3">
                                            <p className="text-xs font-semibold text-slate-200">
                                                {row.is_current ? 'Current session' : (row.revoked_at ? 'Revoked' : 'Session')}
                                            </p>
                                            {!row.is_current && !row.revoked_at ? (
                                                <button
                                                    type="button"
                                                    disabled={sessionsBusy}
                                                    onClick={async () => {
                                                        setSessionsBusy(true)
                                                        try {
                                                            await revokeSession(row.session_id)
                                                            toast.success('Session revoked.')
                                                            refreshSessions()
                                                        } catch (err) {
                                                            toast.error(err?.response?.data?.message || err?.response?.data?.detail || 'Revoke failed.')
                                                        } finally {
                                                            setSessionsBusy(false)
                                                        }
                                                    }}
                                                    className={cn(
                                                        'inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[11px] font-semibold text-slate-200 transition',
                                                        'hover:bg-white/[0.06] hover:text-white',
                                                        'disabled:cursor-not-allowed disabled:opacity-60',
                                                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                                    )}
                                                >
                                                    <Trash2 size={14} className="opacity-80" />
                                                    Revoke
                                                </button>
                                            ) : null}
                                        </div>
                                        <p className="mt-1 text-[11px] text-slate-400">Expires: {row.expires_at || 'n/a'}</p>
                                        <p className="mt-1 truncate text-[11px] text-slate-500">
                                            {row.ip_address ? `IP ${row.ip_address}` : 'IP unknown'}{row.user_agent ? ` | ${row.user_agent}` : ''}
                                        </p>
                                    </div>
                                ))}
                                {!sessions?.length ? <p className="text-sm text-slate-400">No sessions found.</p> : null}
                            </div>
                        </div>
                    </SectionCard>

                    <SectionCard title="API Keys" description="Create keys for programmatic access (X-API-Key header).">
                        <div className="space-y-3">
                            <div className="flex gap-2">
                                <input
                                    value={apiKeyName}
                                    onChange={(e) => setApiKeyName(e.target.value)}
                                    className={cn(
                                        'w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-semibold text-slate-200',
                                        'shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] transition hover:bg-white/[0.06] hover:text-white',
                                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                    )}
                                    placeholder="Key name (optional)"
                                />
                                <button
                                    type="button"
                                    disabled={apiKeysBusy}
                                    onClick={async () => {
                                        setApiKeysBusy(true)
                                        try {
                                            const result = await createApiKey(apiKeyName)
                                            setCreatedKey(result)
                                            setCreatedKeyOpen(true)
                                            setApiKeyName('')
                                            toast.success('API key created.')
                                            refreshApiKeys()
                                        } catch (err) {
                                            toast.error(err?.response?.data?.message || err?.response?.data?.detail || 'API key create failed.')
                                        } finally {
                                            setApiKeysBusy(false)
                                        }
                                    }}
                                    className={cn(
                                        'rounded-2xl bg-gradient-to-r from-cyan-400 to-sky-500 px-4 py-3 text-sm font-semibold text-slate-950 transition',
                                        'shadow-[0_0_0_1px_rgba(34,211,238,0.30),0_18px_45px_rgba(34,211,238,0.16)] hover:brightness-105',
                                        'disabled:cursor-not-allowed disabled:opacity-60',
                                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                    )}
                                >
                                    Create
                                </button>
                            </div>

                            <div className="max-h-72 space-y-2 overflow-auto pr-1">
                                {(apiKeys || []).map((row) => (
                                    <div key={row.key_id} className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                                        <div className="flex items-center justify-between gap-3">
                                            <p className="text-sm font-semibold text-slate-200">{row.name}</p>
                                            {!row.revoked_at ? (
                                                <button
                                                    type="button"
                                                    disabled={apiKeysBusy}
                                                    onClick={async () => {
                                                        setApiKeysBusy(true)
                                                        try {
                                                            await revokeApiKey(row.key_id)
                                                            toast.success('API key revoked.')
                                                            refreshApiKeys()
                                                        } catch (err) {
                                                            toast.error(err?.response?.data?.message || err?.response?.data?.detail || 'Revoke failed.')
                                                        } finally {
                                                            setApiKeysBusy(false)
                                                        }
                                                    }}
                                                    className={cn(
                                                        'inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-[11px] font-semibold text-slate-200 transition',
                                                        'hover:bg-white/[0.06] hover:text-white',
                                                        'disabled:cursor-not-allowed disabled:opacity-60',
                                                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                                    )}
                                                >
                                                    <Trash2 size={14} className="opacity-80" />
                                                    Revoke
                                                </button>
                                            ) : null}
                                        </div>
                                        <p className="mt-1 text-[11px] text-slate-400">Prefix: {row.prefix}</p>
                                        <p className="mt-1 text-[11px] text-slate-500">Created: {row.created_at}</p>
                                        {row.last_used_at ? <p className="mt-1 text-[11px] text-slate-500">Last used: {row.last_used_at}</p> : null}
                                        {row.revoked_at ? <p className="mt-1 text-[11px] text-rose-300">Revoked: {row.revoked_at}</p> : null}
                                    </div>
                                ))}
                                {!apiKeys?.length ? <p className="text-sm text-slate-400">No API keys yet.</p> : null}
                            </div>
                        </div>
                    </SectionCard>

                    <SectionCard title="Exports" description={`Backend base URL: ${getApiBaseURL()}`}>
                        {isAdmin ? (
                            <div className="flex flex-col gap-2">
                                <a
                                    className={cn(
                                        'inline-flex items-center justify-between rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-semibold text-slate-200 transition',
                                        'hover:bg-white/[0.06] hover:text-white',
                                    )}
                                    href={getExportUrl('processed')}
                                    target="_blank"
                                    rel="noreferrer"
                                >
                                    <span>Download processed CSV</span>
                                    <ExternalLink size={16} className="opacity-80" />
                                </a>
                                <a
                                    className={cn(
                                        'inline-flex items-center justify-between rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-semibold text-slate-200 transition',
                                        'hover:bg-white/[0.06] hover:text-white',
                                    )}
                                    href={getExportUrl('raw')}
                                    target="_blank"
                                    rel="noreferrer"
                                >
                                    <span>Download raw CSV</span>
                                    <ExternalLink size={16} className="opacity-80" />
                                </a>
                            </div>
                        ) : (
                            <p className="text-sm text-slate-400">
                                Exports are admin-only. Sign in with an admin account to access CSV downloads.
                            </p>
                        )}
                    </SectionCard>
                </section>

                <section className="mt-6 grid gap-6 md:grid-cols-2">
                    <SectionCard title="Environment" description="Backend runtime and data status.">
                        <div className="space-y-3">
                            <button
                                type="button"
                                disabled={envBusy}
                                onClick={refreshEnv}
                                className={cn(
                                    'inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold text-slate-200 transition',
                                    'hover:bg-white/[0.06] hover:text-white',
                                    'disabled:cursor-not-allowed disabled:opacity-60',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                            >
                                <RefreshCcw size={14} className={cn('opacity-80', envBusy && 'animate-spin')} />
                                Refresh
                            </button>

                            <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-slate-200">
                                <p><span className="text-slate-400">Service:</span> <span className="font-semibold text-white">{metrics?.service || '...'}</span></p>
                                <p className="mt-1"><span className="text-slate-400">Version:</span> {metrics?.version || '...'}</p>
                                <p className="mt-1"><span className="text-slate-400">Environment:</span> {metrics?.environment || '...'}</p>
                                <p className="mt-1"><span className="text-slate-400">Timestamp:</span> {metrics?.timestamp || '...'}</p>
                            </div>

                            <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-slate-200">
                                <p><span className="text-slate-400">Raw rows:</span> <span className="font-semibold text-white">{dataStatus?.raw_rows ?? '...'}</span></p>
                                <p className="mt-1"><span className="text-slate-400">Processed rows:</span> <span className="font-semibold text-white">{dataStatus?.processed_rows ?? '...'}</span></p>
                                <p className="mt-1 truncate"><span className="text-slate-400">Raw path:</span> {dataStatus?.raw_path || '...'}</p>
                                <p className="mt-1 truncate"><span className="text-slate-400">Processed path:</span> {dataStatus?.processed_path || '...'}</p>
                            </div>
                        </div>
                    </SectionCard>

                    <SectionCard title="API Base URL" description="Where the frontend points for API calls.">
                        <div className="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                            <p className="text-sm font-semibold text-slate-200">{getApiBaseURL()}</p>
                            <button
                                type="button"
                                onClick={async () => {
                                    try {
                                        await navigator.clipboard.writeText(getApiBaseURL())
                                        toast.success('Copied API base URL.')
                                    } catch {
                                        toast.error('Copy failed (browser blocked clipboard).')
                                    }
                                }}
                                className={cn(
                                    'inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold text-slate-200 transition',
                                    'hover:bg-white/[0.06] hover:text-white',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                            >
                                <Copy size={14} className="opacity-80" />
                                Copy
                            </button>
                        </div>
                    </SectionCard>
                </section>
            </main>

            <Modal
                open={mfaSetupOpen}
                title="Set up MFA"
                description="Add the secret to your authenticator app, then confirm a 6-digit code."
                onClose={() => setMfaSetupOpen(false)}
            >
                {!mfaSetupPayload ? (
                    <Spinner label="Loading..." />
                ) : (
                    <div className="space-y-4">
                        <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-xs text-slate-200">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Secret (Base32)</p>
                            <p className="mt-2 break-all font-mono text-[12px] text-white">{mfaSetupPayload.secret_base32}</p>
                            <p className="mt-2 text-[11px] text-slate-400">OTPAuth URL (optional):</p>
                            <p className="mt-1 break-all font-mono text-[11px] text-slate-300">{mfaSetupPayload.otpauth_url}</p>
                        </div>

                        <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">Backup codes</p>
                            <div className="mt-2 grid grid-cols-2 gap-2">
                                {(mfaSetupPayload.backup_codes || []).map((code) => (
                                    <code
                                        key={code}
                                        className="rounded-xl border border-white/10 bg-black/30 px-2 py-1 text-[11px] text-slate-200"
                                    >
                                        {code}
                                    </code>
                                ))}
                            </div>
                        </div>

                        <div className="flex flex-col gap-2">
                            <input
                                value={mfaCode}
                                onChange={(e) => setMfaCode(e.target.value)}
                                className={cn(
                                    'w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm font-semibold text-slate-200',
                                    'shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)] transition hover:bg-white/[0.06] hover:text-white',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                                placeholder="6-digit code"
                            />
                            <button
                                type="button"
                                disabled={mfaBusy || !mfaCode.trim()}
                                onClick={async () => {
                                    setMfaBusy(true)
                                    try {
                                        await enableMfa(mfaCode.trim())
                                        toast.success('MFA enabled.')
                                        setMfaSetupOpen(false)
                                        setMfaSetupPayload(null)
                                        setMfaCode('')
                                        refreshMfa()
                                    } catch (err) {
                                        toast.error(err?.response?.data?.message || err?.response?.data?.detail || 'Failed to enable MFA.')
                                    } finally {
                                        setMfaBusy(false)
                                    }
                                }}
                                className={cn(
                                    'inline-flex items-center justify-center rounded-2xl px-4 py-3 text-sm font-semibold transition',
                                    'bg-gradient-to-r from-cyan-400 to-sky-500 text-slate-950 shadow-[0_0_0_1px_rgba(34,211,238,0.30),0_18px_45px_rgba(34,211,238,0.16)]',
                                    'hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60',
                                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                )}
                            >
                                {mfaBusy ? 'Enabling...' : 'Enable MFA'}
                            </button>
                        </div>
                    </div>
                )}
            </Modal>

            <Modal
                open={createdKeyOpen}
                title="API key created"
                description="Copy this API key now. You will not be able to see it again."
                onClose={() => setCreatedKeyOpen(false)}
            >
                {!createdKey ? (
                    <p className="text-sm text-slate-400">No key available.</p>
                ) : (
                    <div className="space-y-3">
                        <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">API key</p>
                            <p className="mt-2 break-all font-mono text-[12px] text-white">{createdKey.api_key}</p>
                        </div>
                        <button
                            type="button"
                            onClick={async () => {
                                try {
                                    await navigator.clipboard.writeText(String(createdKey.api_key || ''))
                                    toast.success('Copied API key.')
                                } catch {
                                    toast.error('Copy failed (browser blocked clipboard).')
                                }
                            }}
                            className={cn(
                                'inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold transition',
                                'border border-white/10 bg-white/[0.04] text-slate-200 hover:bg-white/[0.06] hover:text-white',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                            )}
                        >
                            <Copy size={16} className="opacity-80" />
                            Copy key
                        </button>
                    </div>
                )}
            </Modal>
        </div>
    )
}
