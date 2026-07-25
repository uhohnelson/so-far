import { useCallback, useEffect, useRef, useState } from 'react'
import { api, getToken, setToken, setUnauthorizedHandler } from './api'
import type { LibraryItem, SearchResult, User } from './types'
import Login from './components/Login'
import WatchList from './components/WatchList'
import Discover from './components/Discover'
import Profile from './components/Profile'
import NotFound from './components/NotFound'
import DetailSheet, { type SheetTarget } from './components/DetailSheet'

type Tab = 'shows' | 'movies' | 'discover' | 'profile'

export default function App() {
  const path = window.location.pathname
  const [authed, setAuthed] = useState(() => getToken() !== null)
  const [tab, setTab] = useState<Tab>('shows')
  const [visited, setVisited] = useState<Record<Tab, boolean>>({
    shows: true,
    movies: false,
    discover: false,
    profile: false,
  })
  const [items, setItems] = useState<LibraryItem[] | null>(null)
  const [me, setMe] = useState<User | null>(null)
  const [sheet, setSheet] = useState<SheetTarget | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [markingId, setMarkingId] = useState<number | null>(null)
  const toastTimer = useRef<number | undefined>(undefined)

  useEffect(() => {
    setUnauthorizedHandler(() => setAuthed(false))
  }, [])

  useEffect(() => {
    setVisited((v) => (v[tab] ? v : { ...v, [tab]: true }))
  }, [tab])

  const showToast = useCallback((message: string) => {
    setToast(message)
    window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), 3200)
  }, [])

  const patchItem = useCallback((updated: LibraryItem) => {
    setItems((prev) => {
      if (!prev) return [updated]
      const idx = prev.findIndex((i) => i.id === updated.id)
      if (idx === -1) return [updated, ...prev]
      const next = [...prev]
      next[idx] = updated
      return next
    })
  }, [])

  const removeItem = useCallback((id: number) => {
    setItems((prev) => prev?.filter((i) => i.id !== id) ?? null)
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
    setTab('shows')
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
    if (updated) {
      patchItem(updated)
      if (sheet) setSheet({ kind: 'library', item: updated })
    } else if (sheet?.kind === 'library') {
      removeItem(sheet.item.id)
      setSheet(null)
    }
    if (message) showToast(message)
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
      const added = await api.addToLibrary({
        tmdb_id: result.tmdb_id,
        media_type: result.media_type,
        status: result.media_type === 'tv' ? 'watching' : 'want',
      })
      patchItem(added)
      showToast(`Added ${result.title}`)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Could not add.')
    }
  }

  const markFromList = async (item: LibraryItem) => {
    setMarkingId(item.id)
    try {
      const res = await api.markWatched(item.id)
      patchItem(res.item)
      showToast(res.message)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Could not update.')
    } finally {
      setMarkingId(null)
    }
  }

  const handleCoverChange = async (titleId: number) => {
    try {
      const updated = await api.updateMe({ cover_title_id: titleId })
      setMe(updated)
      showToast('Cover updated')
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Could not update cover.')
    }
  }

  if (path !== '/' && path !== '/index.html') return <NotFound path={path} />
  if (!authed) return <Login onLoggedIn={handleLoggedIn} />

  return (
    <div className="app-bg">
      <div className="shell">
        <div className="tab-panel" hidden={tab !== 'shows'}>
          <WatchList
            mediaType="tv"
            items={items}
            onOpen={(item) => setSheet({ kind: 'library', item })}
            onMark={markFromList}
            onGoDiscover={() => setTab('discover')}
            markingId={markingId}
          />
        </div>
        {visited.movies && (
          <div className="tab-panel" hidden={tab !== 'movies'}>
            <WatchList
              mediaType="movie"
              items={items}
              onOpen={(item) => setSheet({ kind: 'library', item })}
              onMark={markFromList}
              onGoDiscover={() => setTab('discover')}
              markingId={markingId}
            />
          </div>
        )}
        {visited.discover && (
          <div className="tab-panel" hidden={tab !== 'discover'}>
            <Discover
              onOpen={openSearchResult}
              onQuickAdd={quickAdd}
              isAdded={(result) => findInLibrary(result) !== undefined}
            />
          </div>
        )}
        {visited.profile && (
          <div className="tab-panel" hidden={tab !== 'profile'}>
            <Profile
              items={items}
              me={me}
              onOpen={(item) => setSheet({ kind: 'library', item })}
              onCoverChange={handleCoverChange}
              onLogout={handleLogout}
            />
          </div>
        )}

        <nav className="bottom-nav">
          <button
            className={tab === 'shows' ? 'active' : ''}
            onClick={() => setTab('shows')}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="5" width="18" height="13" rx="2" />
              <path d="M8 21h8M12 18v3" />
            </svg>
            Shows
          </button>
          <button
            className={tab === 'movies' ? 'active' : ''}
            onClick={() => setTab('movies')}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18v13H3z" />
              <path d="M7 6V4l3 2 3-2 3 2 3-2v2" />
            </svg>
            Movies
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
