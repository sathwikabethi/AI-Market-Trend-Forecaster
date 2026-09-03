import { useState } from 'react'
import { SendHorizontal } from 'lucide-react'
import { toast } from 'sonner'
import TopNav from '../components/TopNav'
import { cn } from '../lib/cn'
import { askRag } from '../lib/api'

export default function ChatPage({ user, theme, onToggleTheme, onLogout }) {
    const [question, setQuestion] = useState('')
    const [messages, setMessages] = useState([])
    const [sending, setSending] = useState(false)

    const send = async (event) => {
        event.preventDefault()
        const text = question.trim()
        if (!text || sending) return

        setSending(true)
        setMessages((prev) => [...prev, { role: 'user', content: text }])
        setQuestion('')
        try {
            const data = await askRag(text, null, 5)
            setMessages((prev) => [
                ...prev,
                { role: 'assistant', content: data?.answer || 'No answer returned.' },
            ])
        } catch (err) {
            toast.error(err?.response?.data?.message || 'Chat request failed.')
        } finally {
            setSending(false)
        }
    }

    return (
        <div className="min-h-screen bg-tf-bg text-tf-fg">
            <TopNav user={user} theme={theme} onToggleTheme={onToggleTheme} onLogout={onLogout} />

            <main className="mx-auto w-full max-w-6xl px-4 pb-12 pt-8">
                <h1 className="text-3xl font-semibold tracking-tight text-white">AI Chatbot</h1>
                <p className="mt-2 text-sm text-slate-400">
                    Ask questions over processed review data.
                </p>

                <section className="mt-6 overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-white/[0.03] shadow-[0_20px_60px_rgba(0,0,0,0.45)] backdrop-blur">
                    <div className="max-h-[520px] space-y-3 overflow-auto p-6">
                        {messages.length ? messages.map((m, idx) => (
                            <div
                                key={idx}
                                className={cn(
                                    'max-w-[720px] rounded-2xl border px-4 py-3 text-sm leading-relaxed',
                                    m.role === 'user'
                                        ? 'ml-auto border-cyan-400/20 bg-cyan-400/10 text-slate-100'
                                        : 'mr-auto border-white/10 bg-black/20 text-slate-200',
                                )}
                            >
                                {m.content}
                            </div>
                        )) : (
                            <p className="text-sm text-slate-400">
                                Start by asking: &quot;What are the common complaints for sunscreen?&quot;
                            </p>
                        )}
                    </div>

                    <form onSubmit={send} className="flex gap-2 border-t border-white/10 bg-black/20 p-4">
                        <input
                            className="flex-1 rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white placeholder:text-slate-500 outline-none transition focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-400/30"
                            placeholder="Ask a question..."
                            value={question}
                            onChange={(e) => setQuestion(e.target.value)}
                        />
                        <button
                            className={cn(
                                'inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold transition',
                                'bg-gradient-to-r from-cyan-400 to-sky-500 text-slate-950',
                                'hover:from-cyan-300 hover:to-sky-400',
                                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/40',
                                'disabled:cursor-not-allowed disabled:opacity-70',
                            )}
                            type="submit"
                            disabled={sending}
                            aria-label="Send"
                        >
                            <SendHorizontal size={18} />
                        </button>
                    </form>
                </section>
            </main>
        </div>
    )
}
