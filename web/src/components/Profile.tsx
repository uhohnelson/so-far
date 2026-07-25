import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { LibraryItem, Stats, User } from '../types'

interface ProfileProps {
  items: LibraryItem[] | null
  me: User | null
  onOpen: (item: LibraryItem) => void
  onCoverChange: (titleId: number) => void
  onLogout: () => void
}

function splitMinutes(minutes: number) {
  const months = Math.floor(minutes / (30 * 24 * 60))
  const days = Math.floor((minutes % (30 * 24 * 60)) / (24 * 60))
  const hours = Math.floor((minutes % (24 * 60)) / 60)
  return { months, days, hours }
}

function thumbUrl(url: string | null): string | null {
  if (!url) return null
  return url.replace('/w500/', '/w185/')
}

export default function Profile({
  items,
  me,
  onOpen,
  onCoverChange,
  onLogout,
}: ProfileProps) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [pickingCover, setPickingCover] = useState(false)

  useEffect(() => {
    api.stats().then(setStats).catch(() => setStats(null))
  }, [items])

  const displayName = me?.display_name || 'You'
  const initial = displayName.trim().charAt(0).toUpperCase() || 'S'

  const coverCandidates = useMemo(() => {
    const list = items ?? []
    const withArt = list.filter(
      (i) => i.title.backdrop_url || i.title.poster_url,
    )
    // Prefer titles with backdrops; keep unique by title id.
    const seen = new Set<number>()
    const out: LibraryItem[] = []
    for (const item of withArt) {
      if (seen.has(item.title.id)) continue
      seen.add(item.title.id)
      out.push(item)
    }
    out.sort((a, b) => {
      const aScore = a.title.backdrop_url ? 1 : 0
      const bScore = b.title.backdrop_url ? 1 : 0
      return bScore - aScore
    })
    return out
  }, [items])

  const shows = (items ?? []).filter((i) => i.title.media_type === 'tv')
  const movies = (items ?? []).filter((i) => i.title.media_type === 'movie')
  const time = stats ? splitMinutes(stats.minutes) : null

  const coverUrl =
    me?.cover_url ||
    coverCandidates[0]?.title.backdrop_url ||
    coverCandidates[0]?.title.poster_url ||
    null

  return (
    <div className="profile-page">
      <header
        className="profile-cover"
        style={coverUrl ? { backgroundImage: `url(${coverUrl})` } : undefined}
      >
        <div className="profile-cover-shade" />
        <div className="profile-cover-row">
          <div className="profile-avatar" aria-hidden>
            {initial}
          </div>
          <div className="profile-identity">
            <h1>{displayName}</h1>
            <button
              type="button"
              className="profile-edit"
              onClick={() => setPickingCover(true)}
            >
              Change cover
            </button>
          </div>
        </div>
      </header>

      <div className="profile-body">
        <div className="section-label">Stats</div>
        <div className="stat-cards">
          <div className="stat-card">
            <div className="stat-card-label">Watch time</div>
            {time ? (
              <div className="stat-figures">
                {time.months > 0 && (
                  <div className="stat-figure">
                    <strong>{time.months}</strong>
                    <span>{time.months === 1 ? 'month' : 'months'}</span>
                  </div>
                )}
                <div className="stat-figure">
                  <strong>{time.days}</strong>
                  <span>{time.days === 1 ? 'day' : 'days'}</span>
                </div>
                <div className="stat-figure">
                  <strong>{time.hours}</strong>
                  <span>{time.hours === 1 ? 'hour' : 'hours'}</span>
                </div>
              </div>
            ) : (
              <div className="stat-figures">
                <div className="stat-figure">
                  <strong>–</strong>
                </div>
              </div>
            )}
          </div>
          <div className="stat-card">
            <div className="stat-card-label">Watched</div>
            <div className="stat-figures">
              <div className="stat-figure">
                <strong>{stats ? stats.episodes.toLocaleString() : '–'}</strong>
                <span>episodes</span>
              </div>
              <div className="stat-figure">
                <strong>{stats ? stats.movies.toLocaleString() : '–'}</strong>
                <span>movies</span>
              </div>
            </div>
          </div>
        </div>

        {shows.length > 0 && (
          <section className="profile-shelf">
            <div className="section-label">Shows</div>
            <div className="poster-row">
              {shows.slice(0, 16).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="profile-poster"
                  onClick={() => onOpen(item)}
                >
                  {thumbUrl(item.title.poster_url) ? (
                    <img
                      src={thumbUrl(item.title.poster_url)!}
                      alt={item.title.title}
                      loading="lazy"
                    />
                  ) : (
                    <div className="profile-poster-ph">{item.title.title}</div>
                  )}
                </button>
              ))}
            </div>
          </section>
        )}

        {movies.length > 0 && (
          <section className="profile-shelf">
            <div className="section-label">Movies</div>
            <div className="poster-row">
              {movies.slice(0, 16).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="profile-poster"
                  onClick={() => onOpen(item)}
                >
                  {thumbUrl(item.title.poster_url) ? (
                    <img
                      src={thumbUrl(item.title.poster_url)!}
                      alt={item.title.title}
                      loading="lazy"
                    />
                  ) : (
                    <div className="profile-poster-ph">{item.title.title}</div>
                  )}
                </button>
              ))}
            </div>
          </section>
        )}

        <div className="profile-actions">
          <button className="danger" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </div>

      {pickingCover && (
        <>
          <div
            className="sheet-backdrop"
            onClick={() => setPickingCover(false)}
          />
          <div
            className="cover-picker"
            role="dialog"
            aria-label="Choose cover"
          >
            <div className="cover-picker-head">
              <h2>Choose cover</h2>
              <p>Pick artwork from a show or movie on your list.</p>
            </div>
            {coverCandidates.length === 0 ? (
              <div className="empty">Add titles to unlock cover picks.</div>
            ) : (
              <div className="cover-picker-grid">
                {coverCandidates.map((item) => {
                  const art =
                    item.title.backdrop_url || item.title.poster_url
                  const selected = me?.cover_title_id === item.title.id
                  return (
                    <button
                      key={item.title.id}
                      type="button"
                      className={`cover-pick${selected ? ' selected' : ''}`}
                      onClick={() => {
                        onCoverChange(item.title.id)
                        setPickingCover(false)
                      }}
                    >
                      {art ? (
                        <img src={art} alt={item.title.title} loading="lazy" />
                      ) : (
                        <span>{item.title.title}</span>
                      )}
                      <span className="cover-pick-label">{item.title.title}</span>
                    </button>
                  )
                })}
              </div>
            )}
            <button
              type="button"
              className="cover-picker-close"
              onClick={() => setPickingCover(false)}
            >
              Cancel
            </button>
          </div>
        </>
      )}
    </div>
  )
}
