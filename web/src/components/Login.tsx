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
            Open your Sofar bot
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
