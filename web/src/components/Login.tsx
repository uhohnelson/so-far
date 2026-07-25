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
      <div className="mark">S</div>
      <div className="brand">sofar</div>
      <p className="tagline">Track your shows and movies. Know where you left off.</p>

      <ol className="steps">
        <li>Open your Sofar bot in Telegram</li>
        <li>
          Send <code>/app</code>
        </li>
        <li>Type the 6-character code here</li>
      </ol>

      <input
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

      <button
        className="primary-btn"
        onClick={submit}
        disabled={code.trim().length < 4 || busy}
      >
        {busy ? 'Checking…' : 'Sign in'}
      </button>

      {error && <p className="error">{error}</p>}
    </div>
  )
}
