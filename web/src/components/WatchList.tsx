import { useEffect, useMemo, useRef, useState } from 'react'
import {
  episodeName as cachedEpisodeName,
  getCachedSeason,
  loadSeasonEpisodes,
  mapLimit,
} from '../seasonCache'
import type { Episode, LibraryItem, MediaType } from '../types'
import { WatchListSkeleton } from './Skeletons'

function thumbUrl(url: string | null): string | null {
  if (!url) return null
  return url.replace(/\/w(500|342|185)\//, '/w185/')
}

function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null
  const d = new Date(`${dateStr.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(d.getTime())) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const diff = Math.ceil((d.getTime() - today.getTime()) / 86_400_000)
  return diff > 0 ? diff : null
}

type UpcomingRow = {
  key: string
  item: LibraryItem
  days: number
  date: string
  kind: 'movie' | 'episode'
  season?: number
  episode?: number
  episodeName?: string | null
  badge?: string | null
}

function movieUpcoming(item: LibraryItem): UpcomingRow | null {
  if (item.title.media_type !== 'movie') return null
  const date = item.title.release_date
  const days = daysUntil(date)
  if (!date || days == null) return null
  return {
    key: `movie-${item.id}`,
    item,
    days,
    date,
    kind: 'movie',
    episodeName: item.title.title,
    badge: null,
  }
}

function findUpcomingInSeason(
  episodes: Episode[],
  fromEpisode: number,
): Episode | null {
  const sorted = [...episodes].sort((a, b) => a.episode - b.episode)
  for (const ep of sorted) {
    if (ep.episode < fromEpisode) continue
    if (daysUntil(ep.air_date) != null) return ep
  }
  return null
}

function episodeBadge(ep: Episode, seasons: LibraryItem['title']['seasons']): string | null {
  if (ep.episode !== 1) return null
  const numbered = (seasons ?? [])
    .filter((s) => s.season_number >= 1)
    .sort((a, b) => a.season_number - b.season_number)
  if (numbered.length && numbered[0].season_number === ep.season) return 'Premiere'
  return 'Mid-season'
}

function seasonCouldBeUpcoming(airDate: string | null | undefined): boolean {
  // No date → might be TBA; must check episodes.
  if (!airDate) return true
  // Future season premiere → worth fetching.
  if (daysUntil(airDate) != null) return true
  // Already-started seasons can still have unaired episodes (mid-season).
  // Skip only clearly stale seasons (aired more than ~18 months ago).
  const d = new Date(`${airDate.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(d.getTime())) return true
  const cutoff = new Date()
  cutoff.setMonth(cutoff.getMonth() - 18)
  return d >= cutoff
}

async function resolveTvUpcoming(item: LibraryItem): Promise<UpcomingRow | null> {
  if (item.title.media_type !== 'tv') return null
  const seasons = (item.title.seasons ?? [])
    .filter((s) => s.season_number >= 1)
    .sort((a, b) => a.season_number - b.season_number)
  if (!seasons.length) return null

  // Watching: resume from cursor. Want-list with no cursor: start at the
  // latest season so we don't walk S1..Sn of finished catalogue shows.
  const hasCursor = !!(item.current_season && item.current_season >= 1)
  let season = hasCursor
    ? item.current_season!
    : seasons[seasons.length - 1].season_number
  let fromEp = item.current_episode && item.current_episode >= 1
    ? item.current_episode
    : 1

  for (let i = 0; i < seasons.length; i++) {
    const s = seasons[i]
    if (s.season_number < season) continue
    // Skip ancient seasons (no plausible unaired episodes left).
    if (!seasonCouldBeUpcoming(s.air_date)) continue
    const startEp = s.season_number === season ? fromEp : 1
    let episodes = getCachedSeason(item.title.tmdb_id, s.season_number)
    if (!episodes) {
      try {
        episodes = await loadSeasonEpisodes(item.title.tmdb_id, s.season_number)
      } catch {
        continue
      }
    }
    const hit = findUpcomingInSeason(episodes, startEp)
    if (hit) {
      const days = daysUntil(hit.air_date)
      if (days == null || !hit.air_date) continue
      return {
        key: `tv-${item.id}-${hit.season}-${hit.episode}`,
        item,
        days,
        date: hit.air_date,
        kind: 'episode',
        season: hit.season,
        episode: hit.episode,
        episodeName: hit.name,
        badge: episodeBadge(hit, item.title.seasons),
      }
    }
  }
  return null
}

interface WatchListProps {
  mediaType: MediaType
  items: LibraryItem[] | null
  onOpen: (item: LibraryItem) => void
  onMark: (item: LibraryItem) => void
  onGoDiscover: () => void
  markingId: number | null
}

type SubTab = 'watch' | 'want' | 'watched'

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
  mediaType,
  items,
  onOpen,
  onMark,
  onGoDiscover,
  markingId,
}: WatchListProps) {
  const [sub, setSub] = useState<SubTab>('watch')
  const [grid, setGrid] = useState(false)
  const [epNames, setEpNames] = useState<Record<string, string>>({})
  const [upcoming, setUpcoming] = useState<UpcomingRow[] | null>(null)

  const scoped = useMemo(
    () => (items ?? []).filter((i) => i.title.media_type === mediaType),
    [items, mediaType],
  )

  const watching = scoped.filter((i) => {
    if (i.status === 'watching') return true
    // Movies on "want" that are already out live on the watch list.
    if (
      mediaType === 'movie' &&
      i.status === 'want' &&
      daysUntil(i.title.release_date) == null
    ) {
      return true
    }
    return false
  })

  const watched = useMemo(
    () => scoped.filter((i) => i.status === 'watched'),
    [scoped],
  )

  const candidates = useMemo(
    () => scoped.filter((i) => i.status === 'want' || i.status === 'watching'),
    [scoped],
  )

  useEffect(() => {
    let cancelled = false
    const needed = watching.filter(
      (item) =>
        item.title.media_type === 'tv' &&
        item.current_season &&
        item.current_episode,
    )

    // Paint anything already in the shared season cache immediately.
    const seeded: Record<string, string> = {}
    for (const item of needed) {
      const name = cachedEpisodeName(
        item.title.tmdb_id,
        item.current_season!,
        item.current_episode!,
      )
      if (name !== undefined) {
        seeded[
          `${item.title.tmdb_id}:${item.current_season}:${item.current_episode}`
        ] = name
      }
    }
    if (Object.keys(seeded).length) {
      setEpNames((prev) => ({ ...prev, ...seeded }))
    }

    ;(async () => {
      const seasons = new Map<string, { tmdbId: number; season: number }>()
      for (const item of needed) {
        const k = `${item.title.tmdb_id}:${item.current_season}`
        seasons.set(k, {
          tmdbId: item.title.tmdb_id,
          season: item.current_season!,
        })
      }
      await mapLimit([...seasons.values()], 4, async ({ tmdbId, season }) => {
        try {
          await loadSeasonEpisodes(tmdbId, season)
        } catch {
          // leave names blank
        }
      })
      if (cancelled) return
      setEpNames((prev) => {
        const next = { ...prev }
        for (const item of needed) {
          const key = `${item.title.tmdb_id}:${item.current_season}:${item.current_episode}`
          const name = cachedEpisodeName(
            item.title.tmdb_id,
            item.current_season!,
            item.current_episode!,
          )
          next[key] = name ?? ''
        }
        return next
      })
    })()

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items])

  useEffect(() => {
    if (sub !== 'want' || !items) {
      return
    }
    let cancelled = false
    setUpcoming(null)
    ;(async () => {
      const rows = (
        await mapLimit(candidates, 6, async (item) => {
          if (item.title.media_type === 'movie') {
            return movieUpcoming(item)
          }
          return resolveTvUpcoming(item)
        })
      ).filter((row): row is UpcomingRow => row != null)
      if (cancelled) return
      rows.sort((a, b) => a.days - b.days || a.date.localeCompare(b.date))
      setUpcoming(rows)
    })()
    return () => {
      cancelled = true
    }
  }, [sub, items, candidates])

  if (items === null) return <WatchListSkeleton />

  const firstWatching = watching[0]

  const nextEpName = (item: LibraryItem): string | null => {
    if (!item.current_season || !item.current_episode) return null
    const key = `${item.title.tmdb_id}:${item.current_season}:${item.current_episode}`
    const name = epNames[key]
    return name || null
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
          Upcoming
        </button>
        <button
          className={sub === 'watched' ? 'active' : ''}
          onClick={() => setSub('watched')}
        >
          Watched
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
            <div className="big">{mediaType === 'tv' ? '📺' : '🎬'}</div>
            Nothing in your {mediaType === 'tv' ? 'show' : 'movie'} watch list yet.
            <br />
            <button className="primary-btn" onClick={onGoDiscover}>
              Discover {mediaType === 'tv' ? 'shows' : 'movies'}
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
                {thumbUrl(item.title.poster_url) ? (
                  <img
                    src={thumbUrl(item.title.poster_url)!}
                    alt={item.title.title}
                    loading="lazy"
                  />
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
                    {thumbUrl(item.title.poster_url) ? (
                      <img
                        className="thumb"
                        src={thumbUrl(item.title.poster_url)!}
                        alt=""
                        loading="lazy"
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

        {sub === 'want' && upcoming === null && (
          <div className="ep-list" aria-busy="true" aria-label="Loading upcoming">
            {Array.from({ length: 4 }, (_, i) => (
              <div className="skel-ep-card" key={i}>
                <div className="skel skel-thumb" />
                <div className="skel-ep-lines">
                  <div className="skel skel-line w60" />
                  <div className="skel skel-line w40" />
                  <div className="skel skel-line w80" />
                </div>
                <div className="skel skel-check" />
              </div>
            ))}
          </div>
        )}

        {sub === 'want' && upcoming && upcoming.length === 0 && (
          <div className="empty">
            <div className="big">📅</div>
            Nothing upcoming yet.
            <br />
            Add {mediaType === 'tv' ? 'shows' : 'unreleased movies'} to see countdowns here.
          </div>
        )}

        {sub === 'want' && upcoming && upcoming.length > 0 && (
          <div className="ep-list">
            {upcoming.map((row) => (
              <button
                key={row.key}
                type="button"
                className="upcoming-card"
                onClick={() => onOpen(row.item)}
              >
                {thumbUrl(row.item.title.poster_url) ? (
                  <img
                    className="thumb"
                    src={thumbUrl(row.item.title.poster_url)!}
                    alt=""
                    loading="lazy"
                  />
                ) : (
                  <div className="thumb ph">🎬</div>
                )}
                <div className="body">
                  <span className="show-chip">
                    {row.item.title.title}
                    <span className="chev">›</span>
                  </span>
                  {row.kind === 'episode' && row.season != null && row.episode != null ? (
                    <>
                      <div className="ep-code">
                        S{String(row.season).padStart(2, '0')} | E
                        {String(row.episode).padStart(2, '0')}
                        {row.badge && (
                          <span className="upcoming-badge">{row.badge}</span>
                        )}
                      </div>
                      <div className="ep-title">
                        {row.episodeName || 'Episode'}
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="ep-code">
                        Movie
                        <span className="upcoming-badge">Release</span>
                      </div>
                      <div className="ep-title">
                        {row.date.slice(0, 10)}
                      </div>
                    </>
                  )}
                </div>
                <div className="upcoming-days" aria-label={`${row.days} days`}>
                  <strong>{row.days}</strong>
                  <span>{row.days === 1 ? 'day' : 'days'}</span>
                </div>
              </button>
            ))}
          </div>
        )}

        {sub === 'watched' && watched.length === 0 && (
          <div className="empty">
            <div className="big">{mediaType === 'tv' ? '✅' : '🍿'}</div>
            Nothing marked watched yet.
            <br />
            Finish something from your watch list to see it here.
          </div>
        )}

        {sub === 'watched' && watched.length > 0 && (
          <div className="ep-list">
            {watched.map((item) => (
              <button
                key={item.id}
                type="button"
                className="upcoming-card"
                onClick={() => onOpen(item)}
              >
                {thumbUrl(item.title.poster_url) ? (
                  <img
                    className="thumb"
                    src={thumbUrl(item.title.poster_url)!}
                    alt=""
                    loading="lazy"
                  />
                ) : (
                  <div className="thumb ph">🎬</div>
                )}
                <div className="body">
                  <span className="show-chip">
                    {item.title.title}
                    <span className="chev">›</span>
                  </span>
                  <div className="ep-code">
                    {item.title.media_type === 'tv' ? 'Show' : 'Movie'}
                    <span className="upcoming-badge">Watched</span>
                  </div>
                  <div className="ep-title">
                    {item.title.year ? String(item.title.year) : 'Completed'}
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
