import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { LibraryItem } from '../types'

interface WatchListProps {
  items: LibraryItem[] | null
  onOpen: (item: LibraryItem) => void
  onMark: (item: LibraryItem) => void
  onGoDiscover: () => void
  markingId: number | null
}

type SubTab = 'watch' | 'want'

function totalEps(item: LibraryItem): number | null {
  const seasons = item.title.seasons
  if (!seasons) return null
  let total = 0
  for (const s of seasons) {
    if (s.season_number >= 1) total += s.episode_count ?? 0
  }
  return total || null
}

function remainingEps(item: LibraryItem): number | null {
  const seasons = item.title.seasons
  if (!seasons || !item.current_season || !item.current_episode) return null
  let left = 0
  for (const s of seasons) {
    const count = s.episode_count ?? 0
    if (s.season_number > item.current_season) left += count
    else if (s.season_number === item.current_season) {
      left += Math.max(0, count - item.current_episode)
    }
  }
  return left
}

function progressOf(item: LibraryItem): number {
  if (item.title.media_type !== 'tv') return 0
  const total = totalEps(item)
  const rem = remainingEps(item)
  if (!total || rem === null) return 0
  return Math.min(1, Math.max(0, (total - rem - 1) / total))
}

const SWIPE_TRIGGER = 96

function SwipeToMark({
  onMark,
  disabled,
  children,
}: {
  onMark: () => void
  disabled: boolean
  children: React.ReactNode
}) {
  const [offset, setOffset] = useState(0)
  const [swiping, setSwiping] = useState(false)
  const start = useRef<{ x: number; y: number } | null>(null)
  const locked = useRef<'horizontal' | 'vertical' | null>(null)

  const reset = () => {
    start.current = null
    locked.current = null
    setSwiping(false)
    setOffset(0)
  }

  const onTouchStart = (e: React.TouchEvent) => {
    if (disabled) return
    const t = e.touches[0]
    start.current = { x: t.clientX, y: t.clientY }
    locked.current = null
  }

  const onTouchMove = (e: React.TouchEvent) => {
    if (!start.current || disabled) return
    const t = e.touches[0]
    const dx = t.clientX - start.current.x
    const dy = t.clientY - start.current.y

    if (locked.current === null) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return
      locked.current = Math.abs(dx) > Math.abs(dy) ? 'horizontal' : 'vertical'
    }
    if (locked.current === 'vertical') return

    setSwiping(true)
    // Only rightward swipes drag; resist past the trigger point.
    const next = dx <= 0 ? 0 : dx > SWIPE_TRIGGER ? SWIPE_TRIGGER + (dx - SWIPE_TRIGGER) * 0.3 : dx
    setOffset(next)
  }

  const onTouchEnd = () => {
    if (offset >= SWIPE_TRIGGER) onMark()
    reset()
  }

  const armed = offset >= SWIPE_TRIGGER

  return (
    <div className={`swipe-row${armed ? ' armed' : ''}`}>
      <div className="swipe-action" aria-hidden>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
          <path
            d="M5 13l4 4L19 7"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span>Watched</span>
      </div>
      <div
        className="swipe-content"
        style={{
          transform: `translateX(${offset}px)`,
          transition: swiping ? 'none' : 'transform 0.2s ease',
        }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onTouchCancel={reset}
      >
        {children}
      </div>
    </div>
  )
}

export default function WatchList({
  items,
  onOpen,
  onMark,
  onGoDiscover,
  markingId,
}: WatchListProps) {
  const [sub, setSub] = useState<SubTab>('watch')
  const [grid, setGrid] = useState(false)
  const [epNames, setEpNames] = useState<Record<string, string>>({})
  const fetching = useRef<Set<string>>(new Set())

  const watching = (items ?? []).filter((i) => i.status === 'watching')

  useEffect(() => {
    for (const item of watching) {
      if (
        item.title.media_type !== 'tv' ||
        !item.current_season ||
        !item.current_episode
      )
        continue
      const key = `${item.title.tmdb_id}:${item.current_season}:${item.current_episode}`
      if (epNames[key] !== undefined || fetching.current.has(key)) continue
      fetching.current.add(key)
      api
        .seasonEpisodes(item.title.tmdb_id, item.current_season)
        .then((res) => {
          const ep = res.episodes.find(
            (e) => e.episode === item.current_episode,
          )
          setEpNames((prev) => ({ ...prev, [key]: ep?.name || '' }))
        })
        .catch(() => {
          setEpNames((prev) => ({ ...prev, [key]: '' }))
        })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items])

  if (items === null) return <div className="spinner" />

  const want = items.filter((i) => i.status === 'want')
  const firstWatching = watching[0]

  const nextEpName = (item: LibraryItem): string | null => {
    if (!item.current_season || !item.current_episode) return null
    const key = `${item.title.tmdb_id}:${item.current_season}:${item.current_episode}`
    return epNames[key] || null
  }

  return (
    <>
      <div className="tabs">
        <button
          className={sub === 'watch' ? 'active' : ''}
          onClick={() => setSub('watch')}
        >
          Watch list
        </button>
        <button
          className={sub === 'want' ? 'active' : ''}
          onClick={() => setSub('want')}
        >
          List
        </button>
        {sub === 'watch' && watching.length > 0 && (
          <button
            className="view-toggle"
            aria-label={grid ? 'Show as list' : 'Show as grid'}
            onClick={() => setGrid((g) => !g)}
          >
            {grid ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M4 6h16M4 12h16M4 18h16"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                />
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <rect x="4" y="4" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="2" />
                <rect x="13" y="4" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="2" />
                <rect x="4" y="13" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="2" />
                <rect x="13" y="13" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="2" />
              </svg>
            )}
          </button>
        )}
      </div>

      <div className="page">
        {sub === 'watch' && firstWatching && !grid && (
          <button className="watch-next" onClick={() => onOpen(firstWatching)}>
            Watch next
          </button>
        )}

        {sub === 'watch' && watching.length === 0 && (
          <div className="empty">
            <div className="big">📺</div>
            Nothing in Watching yet.
            <br />
            <button className="primary-btn" onClick={onGoDiscover}>
              Discover shows
            </button>
          </div>
        )}

        {sub === 'watch' && watching.length > 0 && grid && (
          <div className="library-grid">
            {watching.map((item) => (
              <button
                key={item.id}
                className="grid-card"
                onClick={() => onOpen(item)}
              >
                {item.title.poster_url ? (
                  <img src={item.title.poster_url} alt={item.title.title} />
                ) : (
                  <div className="grid-ph">{item.title.title}</div>
                )}
                {item.title.media_type === 'tv' && (
                  <div className="grid-progress">
                    <div
                      className="grid-progress-fill"
                      style={{ width: `${Math.round(progressOf(item) * 100)}%` }}
                    />
                  </div>
                )}
              </button>
            ))}
          </div>
        )}

        {sub === 'watch' && watching.length > 0 && !grid && (
          <div className="ep-list">
            {watching.map((item) => {
              const rem = remainingEps(item)
              const isTv = item.title.media_type === 'tv'
              const epName = nextEpName(item)
              return (
                <SwipeToMark
                  key={item.id}
                  disabled={markingId === item.id}
                  onMark={() => onMark(item)}
                >
                <div className="ep-card">
                  <button
                    type="button"
                    className="ep-main"
                    onClick={() => onOpen(item)}
                  >
                    {item.title.poster_url ? (
                      <img
                        className="thumb"
                        src={item.title.poster_url}
                        alt=""
                      />
                    ) : (
                      <div className="thumb ph">🎬</div>
                    )}
                    <div className="body">
                      <span className="show-chip">
                        {item.title.title}
                        <span className="chev">›</span>
                      </span>
                      {isTv && item.current_season && item.current_episode ? (
                        <>
                          <div className="ep-code">
                            S{String(item.current_season).padStart(2, '0')} | E
                            {String(item.current_episode).padStart(2, '0')}
                            {rem !== null && rem > 0 && (
                              <span className="rem"> +{rem}</span>
                            )}
                          </div>
                          <div className="ep-title">
                            {epName || 'Open details'}
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="ep-code">Movie</div>
                          <div className="ep-title">Tap check when done</div>
                        </>
                      )}
                    </div>
                  </button>
                  <button
                    className={`check-btn${markingId === item.id ? ' done' : ''}`}
                    aria-label={`Mark ${item.title.title} watched`}
                    disabled={markingId === item.id}
                    onClick={() => onMark(item)}
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                      <path
                        d="M5 13l4 4L19 7"
                        stroke="currentColor"
                        strokeWidth="3"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>
                </div>
                </SwipeToMark>
              )
            })}
          </div>
        )}

        {sub === 'want' && want.length === 0 && (
          <div className="empty">
            <div className="big">✨</div>
            Your list is empty.
          </div>
        )}

        {sub === 'want' && want.length > 0 && (
          <div className="ep-list">
            {want.map((item) => (
              <button
                key={item.id}
                className="want-card"
                onClick={() => onOpen(item)}
              >
                {item.title.poster_url ? (
                  <img className="thumb" src={item.title.poster_url} alt="" />
                ) : (
                  <div className="thumb ph">🎬</div>
                )}
                <div>
                  <div className="name">{item.title.title}</div>
                  <div className="meta">
                    {[
                      item.title.year,
                      item.title.media_type === 'tv' ? 'Show' : 'Movie',
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
