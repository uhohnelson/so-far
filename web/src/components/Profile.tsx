import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import type { LibraryItem, Stats, User } from '../types'
import PosterGridSheet from './PosterGridSheet'

interface ProfileProps {
  items: LibraryItem[] | null
  me: User | null
  onOpen: (item: LibraryItem) => void
  onCoverChange: (titleId: number) => void
  onTimezoneChange: (timezone: string) => void
  onLogout: () => void
}

const TIMEZONE_OPTIONS = [
  { label: 'Eastern (US)', value: 'America/New_York' },
  { label: 'Central (US)', value: 'America/Chicago' },
  { label: 'Mountain (US)', value: 'America/Denver' },
  { label: 'Pacific (US)', value: 'America/Los_Angeles' },
  { label: 'London (GMT/BST)', value: 'Europe/London' },
  { label: 'Paris (CET)', value: 'Europe/Paris' },
  { label: 'Tokyo (JST)', value: 'Asia/Tokyo' },
  { label: 'Sydney (AEST)', value: 'Australia/Sydney' },
  { label: 'Ghana (GMT)', value: 'Africa/Accra' },
]

function TimezonePicker({
  value,
  onChange,
}: {
  value: string | null
  onChange: (timezone: string) => void
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (rootRef.current?.contains(event.target as Node)) return
      setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  const selectedLabel = value
    ? (TIMEZONE_OPTIONS.find((opt) => opt.value === value)?.label ?? value)
    : null

  return (
    <div className="tz-picker" ref={rootRef}>
      <button
        type="button"
        id="profile-timezone"
        className={`tz-picker-trigger${!value ? ' is-placeholder' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span>{selectedLabel ?? 'Pick a timezone'}</span>
        <span className="tz-picker-caret" aria-hidden>{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <ul className="tz-picker-menu" role="listbox" aria-labelledby="profile-timezone">
          {TIMEZONE_OPTIONS.map((opt) => (
            <li key={opt.value}>
              <button
                type="button"
                role="option"
                aria-selected={value === opt.value}
                className={value === opt.value ? 'selected' : ''}
                onClick={() => {
                  onChange(opt.value)
                  setOpen(false)
                }}
              >
                {opt.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function splitMinutes(minutes: number) {
  const months = Math.floor(minutes / (30 * 24 * 60))
  const days = Math.floor((minutes % (30 * 24 * 60)) / (24 * 60))
  const hours = Math.floor((minutes % (24 * 60)) / 60)
  return { months, days, hours }
}

function thumbUrl(url: string | null): string | null {
  if (!url) return null
  return url.replace(/\/w(500|342|185)\//, '/w185/')
}

export default function Profile({
  items,
  me,
  onOpen,
  onCoverChange,
  onTimezoneChange,
  onLogout,
}: ProfileProps) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [pickingCover, setPickingCover] = useState(false)
  const [gridFilter, setGridFilter] = useState<'tv' | 'movie' | null>(null)

  const gridItems = useMemo(() => {
    if (!gridFilter || !items) return null
    return items.filter((i) => i.title.media_type === gridFilter)
  }, [gridFilter, items])

  const gridTitle =
    gridFilter === 'tv' ? 'Shows' : gridFilter === 'movie' ? 'Movies' : null

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

  const openGrid = (filter: 'tv' | 'movie') => {
    setGridFilter(filter)
  }

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
        <div className="profile-timezone">
          <label htmlFor="profile-timezone">Alert timezone</label>
          <TimezonePicker
            value={me?.timezone ?? null}
            onChange={onTimezoneChange}
          />
        </div>

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
            <div className="section-label">
              Shows
              {shows.length > 8 && (
                <button
                  type="button"
                  className="see-all"
                  onClick={() => openGrid('tv')}
                >
                  See more
                </button>
              )}
            </div>
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
            <div className="section-label">
              Movies
              {movies.length > 8 && (
                <button
                  type="button"
                  className="see-all"
                  onClick={() => openGrid('movie')}
                >
                  See more
                </button>
              )}
            </div>
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
      </div>

      <button type="button" className="profile-signout-bar" onClick={onLogout}>
        Sign out
      </button>

      {gridTitle && gridItems && (
        <PosterGridSheet
          title={gridTitle}
          items={gridItems}
          onClose={() => setGridFilter(null)}
          onOpen={(item) => {
            if ('title' in item && typeof item.title === 'object' && 'status' in item) {
              setGridFilter(null)
              onOpen(item as LibraryItem)
            }
          }}
        />
      )}

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
