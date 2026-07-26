import { useState } from 'react'
import { api, setToken } from '../api'

export default function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (code.trim().length < 4 || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.exchangeCode(code.trim())
      setToken(res.token)
      onLoggedIn()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <header className="login-hero">
        <div className="login-brand">sofar</div>
        <p className="login-tagline">Track shows. Know where you left off.</p>
      </header>

      <main className="login-body">
        <h1 className="login-title">Sign in</h1>
        <p className="login-lead">
          Get a code from the Telegram bot, then enter it below.
        </p>

        <ol className="login-steps">
          <li>
            Open your{' '}
            <a
              className="login-bot-link"
              href="https://t.me/sofarwatch_bot"
              target="_blank"
              rel="noopener noreferrer"
              title="Opens @sofarwatch_bot in Telegram"
              aria-label="Open Sofar bot in Telegram (@sofarwatch_bot)"
            >
              Sofar bot
              <svg
                className="login-bot-link-icon"
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
            </a>
          </li>
          <li>
            Send <code>/app</code>
          </li>
          <li>Enter the 6-character code</li>
        </ol>

        <label className="login-label" htmlFor="login-code">
          Code
        </label>
        <input
          id="login-code"
          className="code-input"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          maxLength={6}
          placeholder="······"
          autoFocus
          autoComplete="one-time-code"
          inputMode="text"
          aria-label="Login code"
        />

        {error && <p className="login-error">{error}</p>}
      </main>

      <button
        type="button"
        className="login-submit"
        onClick={submit}
        disabled={code.trim().length < 4 || busy}
      >
        {busy ? 'Checking…' : 'Sign in'}
      </button>
    </div>
  )
}
