import { useCallback, useEffect, useRef, useState } from 'react'
import { api, getToken, setToken, setUnauthorizedHandler } from './api'
import type { LibraryItem, SearchResult, User } from './types'
import Login from './components/Login'
import WatchList from './components/WatchList'
import Discover from './components/Discover'
import Profile from './components/Profile'
import NotFound from './components/NotFound'
import DetailSheet, { type SheetTarget } from './components/DetailSheet'

type Tab = 'episodes' | 'discover' | 'profile'

export default function App() {
  const path = window.location.pathname
  const [authed, setAuthed] = useState(() => getToken() !== null)
  const [tab, setTab] = useState<Tab>('episodes')
  const [items, setItems] = useState<LibraryItem[] | null>(null)
  const [me, setMe] = useState<User | null>(null)
  const [sheet, setSheet] = useState<SheetTarget | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [markingId, setMarkingId] = useState<number | null>(null)
  const toastTimer = useRef<number | undefined>(undefined)

  useEffect(() => {
    setUnauthorizedHandler(() => setAuthed(false))
  }, [])

  const showToast = useCallback((message: string) => {
    setToast(message)
    window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), 3200)
  }, [])

  const refreshLibrary = useCallback(async () => {
    try {
      const [library, user] = await Promise.all([api.library(), api.me()])
      setItems(library)
      setMe(user)
    } catch (err) {
      if (err instanceof Error && err.message !== 'Signed out') {
        showToast(err.message)
      }
    }
  }, [showToast])

  useEffect(() => {
    if (authed) refreshLibrary()
    else {
      setItems(null)
      setMe(null)
    }
  }, [authed, refreshLibrary])

  const handleLoggedIn = () => {
    setAuthed(true)
    setTab('episodes')
  }

  const handleLogout = async () => {
    try {
      await api.logout()
    } catch {
      // ignore
    }
    setToken(null)
    setAuthed(false)
    setSheet(null)
  }

  const handleMutated = (updated: LibraryItem | null, message?: string) => {
    refreshLibrary()
    if (message) showToast(message)
    if (sheet) {
      setSheet(updated ? { kind: 'library', item: updated } : null)
    }
  }

  const openSearchResult = (result: SearchResult) => {
    const existing = items?.find(
      (i) =>
        i.title.tmdb_id === result.tmdb_id &&
        i.title.media_type === result.media_type,
    )
    setSheet(
      existing
        ? { kind: 'library', item: existing }
        : { kind: 'search', result },
    )
  }

  const findInLibrary = (result: SearchResult) =>
    items?.find(
      (i) =>
        i.title.tmdb_id === result.tmdb_id &&
        i.title.media_type === result.media_type,
    )

  const quickAdd = async (result: SearchResult) => {
    try {
      const existing = findInLibrary(result)
      if (existing) {
        showToast(`Already on your list`)
        return
      }
      await api.addToLibrary({
        tmdb_id: result.tmdb_id,
        media_type: result.media_type,
        status: result.media_type === 'tv' ? 'watching' : 'want',
      })
      await refreshLibrary()
      showToast(`Added ${result.title}`)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Could not add.')
    }
  }

  const markFromList = async (item: LibraryItem) => {
    setMarkingId(item.id)
    try {
      const res = await api.markWatched(item.id)
      await refreshLibrary()
      showToast(res.message)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Could not update.')
    } finally {
      setMarkingId(null)
    }
  }

  if (path !== '/' && path !== '/index.html') return <NotFound path={path} />
  if (!authed) return <Login onLoggedIn={handleLoggedIn} />

  return (
    <div className="app-bg">
      <div className="shell">
        {tab === 'episodes' && (
          <WatchList
            items={items}
            onOpen={(item) => setSheet({ kind: 'library', item })}
            onMark={markFromList}
            onGoDiscover={() => setTab('discover')}
            markingId={markingId}
          />
        )}
        {tab === 'discover' && (
          <Discover
            onOpen={openSearchResult}
            onQuickAdd={quickAdd}
            isAdded={(result) => findInLibrary(result) !== undefined}
          />
        )}
        {tab === 'profile' && (
          <Profile
            items={items}
            displayName={me?.display_name ?? null}
            onOpen={(item) => setSheet({ kind: 'library', item })}
            onLogout={handleLogout}
          />
        )}

        <nav className="bottom-nav">
          <button
            className={tab === 'episodes' ? 'active' : ''}
            onClick={() => setTab('episodes')}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 11l3 3L22 4" />
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
            </svg>
            Episodes
          </button>
          <button
            className={tab === 'discover' ? 'active' : ''}
            onClick={() => setTab('discover')}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            Discover
          </button>
          <button
            className={tab === 'profile' ? 'active' : ''}
            onClick={() => setTab('profile')}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="8" r="4" />
              <path d="M4 20c1.5-4 14.5-4 16 0" />
            </svg>
            Profile
          </button>
        </nav>

        {sheet && (
          <DetailSheet
            target={sheet}
            onClose={() => setSheet(null)}
            onMutated={handleMutated}
            onError={showToast}
          />
        )}

        {toast && <div className="toast">{toast}</div>}
      </div>
    </div>
  )
}
