import { useEffect, useState } from 'react'
import { api } from '../api'
import type { LibraryItem, Stats } from '../types'

interface ProfileProps {
  items: LibraryItem[] | null
  displayName: string | null
  onOpen: (item: LibraryItem) => void
  onLogout: () => void
}

function splitMinutes(minutes: number) {
  const months = Math.floor(minutes / (30 * 24 * 60))
  const days = Math.floor((minutes % (30 * 24 * 60)) / (24 * 60))
  const hours = Math.floor((minutes % (24 * 60)) / 60)
  return { months, days, hours }
}

export default function Profile({
  items,
  displayName,
  onOpen,
  onLogout,
}: ProfileProps) {
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => {
    api.stats().then(setStats).catch(() => setStats(null))
  }, [items])

  const watched = items?.filter((i) => i.status === 'watched') ?? []
  const counts = {
    list: items?.filter((i) => i.status === 'want').length ?? 0,
    watching: items?.filter((i) => i.status === 'watching').length ?? 0,
    watched: watched.length,
  }
  const time = stats ? splitMinutes(stats.minutes) : null

  return (
    <div className="page">
      <div className="profile-head">
        <h1>{displayName || 'You'}</h1>
        <p>
          {counts.watching} watching · {counts.list} on list · {counts.watched}{' '}
          watched
        </p>
      </div>

      <div className="section-label">Stats</div>
      <div className="stat-cards">
        <div className="stat-card">
          <div className="stat-card-label">📺 Watch time</div>
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
          <div className="stat-card-label">✓ Watched</div>
          <div className="stat-figures">
            <div className="stat-figure">
              <strong>{stats ? stats.episodes : '–'}</strong>
              <span>episodes</span>
            </div>
            <div className="stat-figure">
              <strong>{stats ? stats.movies : '–'}</strong>
              <span>movies</span>
            </div>
          </div>
        </div>
      </div>

      {watched.length > 0 && (
        <>
          <div className="section-label">Watched</div>
          <div className="ep-list">
            {watched.slice(0, 12).map((item) => (
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
                    {[item.title.year, item.title.media_type === 'tv' ? 'Show' : 'Movie']
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </>
      )}

      <div className="profile-actions">
        <button className="danger" onClick={onLogout}>
          Sign out
        </button>
      </div>
    </div>
  )
}
