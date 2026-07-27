import { useEffect, useState } from 'react'
import { api } from '../api'
import {
  getCachedSeason,
  invalidateCachedSeason,
  loadSeasonEpisodes,
  setCachedSeason,
} from '../seasonCache'
import type {
  Episode,
  LibraryItem,
  MediaType,
  SearchResult,
  Title,
  TitleDetail,
} from '../types'
import { DetailBodySkeleton, SeasonEpisodesSkeleton } from './Skeletons'
import PersonSheet from './PersonSheet'

export type SheetTarget =
  | { kind: 'library'; item: LibraryItem }
  | { kind: 'search'; result: SearchResult }

interface DetailSheetProps {
  target: SheetTarget
  onClose: () => void
  onMutated: (updated: LibraryItem | null, message?: string) => void
  onError: (message: string) => void
  onOpenSearch?: (result: SearchResult) => void
}

function emptyTitle(partial: Partial<Title> & Pick<Title, 'tmdb_id' | 'media_type' | 'title'>): Title {
  return {
    id: 0,
    year: null,
    overview: null,
    poster_url: null,
    backdrop_url: null,
    tagline: null,
    genres: [],
    runtime: null,
    status: null,
    vote_average: null,
    networks: [],
    number_of_seasons: null,
    number_of_episodes: null,
    seasons: null,
    cast: [],
    release_date: null,
    trailer_url: null,
    providers: [],
    ...partial,
  }
}

function seedFromTarget(target: SheetTarget): TitleDetail {
  if (target.kind === 'library') {
    return {
      title: target.item.title,
      library_item: target.item,
      watched_episodes: [],
    }
  }
  const r = target.result
  return {
    title: emptyTitle({
      tmdb_id: r.tmdb_id,
      media_type: r.media_type,
      title: r.title,
      year: r.year,
      overview: r.overview,
      poster_url: r.poster_url,
      backdrop_url: r.backdrop_url,
    }),
    library_item: null,
    watched_episodes: [],
  }
}

export default function DetailSheet({
  target,
  onClose,
  onMutated,
  onError,
  onOpenSearch,
}: DetailSheetProps) {
  const seedType: MediaType =
    target.kind === 'library'
      ? target.item.title.media_type
      : target.result.media_type
  const seedId =
    target.kind === 'library'
      ? target.item.title.tmdb_id
      : target.result.tmdb_id

  const [detail, setDetail] = useState<TitleDetail>(() => seedFromTarget(target))
  const [hydrating, setHydrating] = useState(true)
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState<'about' | 'episodes'>(
    seedType === 'tv' ? 'episodes' : 'about',
  )
  const [openSeason, setOpenSeason] = useState<number | null>(null)
  const [episodesBySeason, setEpisodesBySeason] = useState<
    Record<number, Episode[] | 'loading'>
  >({})
  const [confirm, setConfirm] = useState<{
    season: number
    episode: number
    previous: number
  } | null>(null)
  const [personId, setPersonId] = useState<number | null>(null)
  const [personName, setPersonName] = useState('')

  const loadSeason = async (tmdbId: number, seasonNumber: number) => {
    const cached = getCachedSeason(tmdbId, seasonNumber)
    if (cached) {
      setEpisodesBySeason((prev) => ({ ...prev, [seasonNumber]: cached }))
      return
    }
    setEpisodesBySeason((prev) => ({ ...prev, [seasonNumber]: 'loading' }))
    try {
      const episodes = await loadSeasonEpisodes(tmdbId, seasonNumber)
      setEpisodesBySeason((prev) => ({ ...prev, [seasonNumber]: episodes }))
    } catch {
      setCachedSeason(tmdbId, seasonNumber, [])
      setEpisodesBySeason((prev) => ({ ...prev, [seasonNumber]: [] }))
    }
  }

  const reloadSeasonsUpTo = async (tmdbId: number, throughSeason: number) => {
    const seasons = detail?.title.seasons || []
    const numbers = seasons
      .map((s) => s.season_number)
      .filter((n) => n <= throughSeason)
    const targets = numbers.length ? numbers : [throughSeason]
    await Promise.all(targets.map((n) => loadSeason(tmdbId, n)))
  }

  const refreshDetail = async (tmdbId: number, mediaType: MediaType) => {
    const refreshed = await api.titleDetail(mediaType, tmdbId)
    setDetail(refreshed)
    return refreshed
  }

  useEffect(() => {
    let cancelled = false
    setDetail(seedFromTarget(target))
    setHydrating(true)
    setOpenSeason(null)
    setEpisodesBySeason({})
    setTab(seedType === 'tv' ? 'episodes' : 'about')
    setConfirm(null)
    ;(async () => {
      try {
        const d = await api.titleDetail(seedType, seedId)
        if (cancelled) return
        setDetail(d)
        setTab(d.title.media_type === 'tv' ? 'episodes' : 'about')
      } catch (err) {
        if (cancelled) return
        onError(err instanceof Error ? err.message : 'Could not load title.')
        onClose()
      } finally {
        if (!cancelled) setHydrating(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedType, seedId])

  const toggleSeason = (seasonNumber: number) => {
    if (openSeason === seasonNumber) {
      setOpenSeason(null)
      return
    }
    setOpenSeason(seasonNumber)
    if (!detail) return
    if (episodesBySeason[seasonNumber] == null) {
      loadSeason(detail.title.tmdb_id, seasonNumber)
    }
  }

  const title: Title | null = detail?.title ?? null
  const item = detail?.library_item ?? null
  const watchedKeys = detail?.watched_episodes ?? []

  const episodeKey = (season: number, episode: number) =>
    `S${season}E${episode}`

  const isEpisodeWatched = (season: number, episode: number) =>
    watchedKeys.includes(episodeKey(season, episode))

  const patchSeasonWatched = (
    seasonNumber: number,
    patch: (ep: Episode) => Episode,
  ) => {
    setEpisodesBySeason((prev) => {
      const cached = prev[seasonNumber]
      if (!cached || cached === 'loading') return prev
      const next = cached.map(patch)
      if (title) setCachedSeason(title.tmdb_id, seasonNumber, next)
      return { ...prev, [seasonNumber]: next }
    })
  }

  const applyWatchedKeys = (keys: string[]) => {
    setDetail((prev) =>
      prev ? { ...prev, watched_episodes: keys } : prev,
    )
    if (!title) return
    const seasons = new Set<number>()
    for (const k of keys) {
      const m = /^S(\d+)E(\d+)$/.exec(k)
      if (m) seasons.add(Number(m[1]))
    }
    for (const seasonNumber of seasons) {
      patchSeasonWatched(seasonNumber, (ep) => ({
        ...ep,
        watched: keys.includes(episodeKey(ep.season, ep.episode)),
      }))
    }
  }
  const hero = title?.backdrop_url || title?.poster_url

  const seasonProgress = (seasonNumber: number, episodeCount: number | null) => {
    const total = episodeCount ?? 0
    const watched = watchedKeys.filter((k) =>
      k.startsWith(`S${seasonNumber}E`),
    ).length
    return { watched, total }
  }

  const overallProgress = () => {
    if (!title?.seasons?.length) return 0
    let watched = 0
    let total = 0
    for (const s of title.seasons) {
      const p = seasonProgress(s.season_number, s.episode_count)
      watched += p.watched
      total += p.total
    }
    return total > 0 ? watched / total : 0
  }

  const ensureLibrary = async () => {
    if (!title) return null
    if (item) return item
    const lib = await api.addToLibrary({
      tmdb_id: title.tmdb_id,
      media_type: title.media_type,
      status: 'watching',
    })
    setDetail({
      title: lib.title,
      library_item: lib,
      watched_episodes: detail?.watched_episodes ?? [],
    })
    return lib
  }

  const run = async (fn: () => Promise<void>) => {
    if (busy) return
    setBusy(true)
    try {
      await fn()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  const add = () =>
    run(async () => {
      if (!title) return
      const status =
        title.media_type === 'tv'
          ? 'watching'
          : daysUntil(title.release_date) != null
            ? 'want'
            : 'watching'
      const updated = await api.addToLibrary({
        tmdb_id: title.tmdb_id,
        media_type: title.media_type,
        status,
      })
      setDetail({
        title: updated.title,
        library_item: updated,
        watched_episodes: detail?.watched_episodes ?? [],
      })
      onMutated(updated, `Added ${title.title}`)
    })

  const remove = () =>
    run(async () => {
      if (!item || !title) return
      if (!window.confirm(`Remove ${title.title} from your list?`)) return
      await api.removeFromLibrary(item.id)
      setDetail({ title, library_item: null, watched_episodes: [] })
      onMutated(null, `Removed ${title.title}`)
    })

  const markMovie = () =>
    run(async () => {
      if (!title) return
      let lib = item
      if (!lib) {
        lib = await api.addToLibrary({
          tmdb_id: title.tmdb_id,
          media_type: 'movie',
          status: 'watching',
        })
      }
      const res = await api.markWatched(lib.id)
      setDetail({
        title: res.item.title,
        library_item: res.item,
        watched_episodes: [],
      })
      onMutated(res.item, res.message)
    })

  const markEpisodeCore = async (
    s: number,
    e: number,
    markPrevious: boolean,
    libraryId?: number,
  ) => {
    if (!title) return
    let libId = libraryId ?? item?.id
    if (!libId) {
      const lib = await api.addToLibrary({
        tmdb_id: title.tmdb_id,
        media_type: 'tv',
        status: 'watching',
        current_season: s,
        current_episode: e,
      })
      libId = lib.id
    }
    const res = await api.markEpisode(libId, s, e, markPrevious)
    const refreshed = await refreshDetail(title.tmdb_id, 'tv')
    applyWatchedKeys(refreshed.watched_episodes)
    invalidateCachedSeason(title.tmdb_id, s)
    if (markPrevious) await reloadSeasonsUpTo(title.tmdb_id, s)
    else await loadSeason(title.tmdb_id, s)
    onMutated(res.item, res.message)
    setConfirm(null)
  }

  const doMarkEpisode = (s: number, e: number, markPrevious: boolean) =>
    run(() => markEpisodeCore(s, e, markPrevious))

  const onToggleEpisode = async (ep: Episode) => {
    if (!title || busy) return
    if (isEpisodeWatched(ep.season, ep.episode)) {
      if (!item) return
      await run(async () => {
        const res = await api.unmarkEpisode(item.id, ep.season, ep.episode)
        const refreshed = await refreshDetail(title.tmdb_id, 'tv')
        applyWatchedKeys(refreshed.watched_episodes)
        invalidateCachedSeason(title.tmdb_id, ep.season)
        await loadSeason(title.tmdb_id, ep.season)
        onMutated(res.item)
      })
      return
    }

    setBusy(true)
    try {
      let libId = item?.id
      if (!libId) {
        const lib = await api.addToLibrary({
          tmdb_id: title.tmdb_id,
          media_type: 'tv',
          status: 'watching',
          current_season: ep.season,
          current_episode: ep.episode,
        })
        libId = lib.id
        setDetail({
          title: lib.title,
          library_item: lib,
          watched_episodes: [],
        })
      }
      const preview = await api.previewMark(libId, ep.season, ep.episode)
      if (preview.previous_unwatched > 0) {
        setConfirm({
          season: ep.season,
          episode: ep.episode,
          previous: preview.previous_unwatched,
        })
      } else {
        await markEpisodeCore(ep.season, ep.episode, false, libId)
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  const onToggleSeason = (seasonNumber: number, complete: boolean) =>
    run(async () => {
      if (!title) return
      const lib = await ensureLibrary()
      if (!lib) return
      if (complete) {
        const res = await api.unmarkSeason(lib.id, seasonNumber)
        const refreshed = await refreshDetail(title.tmdb_id, 'tv')
        applyWatchedKeys(refreshed.watched_episodes)
        invalidateCachedSeason(title.tmdb_id, seasonNumber)
        if (episodesBySeason[seasonNumber]) {
          await loadSeason(title.tmdb_id, seasonNumber)
        }
        onMutated(res.item)
      } else {
        const res = await api.markSeason(lib.id, seasonNumber)
        const refreshed = await refreshDetail(title.tmdb_id, 'tv')
        applyWatchedKeys(refreshed.watched_episodes)
        invalidateCachedSeason(title.tmdb_id, seasonNumber)
        if (episodesBySeason[seasonNumber]) {
          await loadSeason(title.tmdb_id, seasonNumber)
        }
        onMutated(res.item, res.message)
      }
    })

  const onMarkAll = () =>
    run(async () => {
      if (!title) return
      const lib = await ensureLibrary()
      if (!lib) return
      const res = await api.markAllSeasons(lib.id)
      const refreshed = await refreshDetail(title.tmdb_id, 'tv')
      applyWatchedKeys(refreshed.watched_episodes)
      setEpisodesBySeason({})
      if (openSeason != null) await loadSeason(title.tmdb_id, openSeason)
      onMutated(res.item, res.message)
    })

  const metaLine = (t: Title) => {
    const bits: string[] = []
    if (t.year) bits.push(String(t.year))
    if (t.media_type === 'tv') {
      if (t.number_of_seasons)
        bits.push(
          `${t.number_of_seasons} season${t.number_of_seasons === 1 ? '' : 's'}`,
        )
      if (t.networks[0]) bits.push(t.networks[0])
    } else if (t.runtime) {
      bits.push(`${t.runtime} min`)
    }
    if (t.status) bits.push(t.status)
    return bits.join(' · ')
  }

  const formatDate = (iso: string) => {
    const d = new Date(`${iso}T00:00:00`)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  }

  const daysUntil = (airDate: string | null): number | null => {
    if (!airDate) return null
    const d = new Date(`${airDate}T00:00:00`)
    if (Number.isNaN(d.getTime())) return null
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const diff = Math.ceil((d.getTime() - today.getTime()) / 86_400_000)
    return diff > 0 ? diff : null
  }

  const stars = (vote: number) => {
    const filled = Math.round(vote / 2)
    return '★★★★★'.slice(0, filled) + '☆☆☆☆☆'.slice(0, 5 - filled)
  }

  const movieWatched =
    title?.media_type === 'movie' && item?.status === 'watched'

  const CheckIcon = () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <path
        d="M5 13l4 4L19 7"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )

  return (
    <>
      <div className="sheet-backdrop" onClick={onClose} />
      <div
        className={`sheet${!item && title ? ' has-add-bar' : ''}${item ? ' has-action-bar' : ''}`}
        role="dialog"
        aria-label={title?.title || 'Title'}
      >
        {title ? (
          <>
            <div className="sheet-scroll">
            <div
              className="hero"
              style={hero ? { backgroundImage: `url(${hero})` } : undefined}
            >
              <div className="hero-top">
                <button className="icon-btn" onClick={onClose} aria-label="Close">
                  ←
                </button>
              </div>
              <div className="hero-copy">
                <h2>{title.title}</h2>
                <div className="meta">{metaLine(title)}</div>
                {title.vote_average != null && title.vote_average > 0 && (
                  <div className="rating">
                    ★ {title.vote_average.toFixed(1)}
                  </div>
                )}
              </div>
            </div>

            {hydrating && !title.seasons && title.media_type === 'tv' ? (
              <DetailBodySkeleton />
            ) : (
              <>
            <div
              className="progress-rule"
              role="progressbar"
              aria-valuenow={Math.round(overallProgress() * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="progress-rule-fill"
                style={{ width: `${Math.round(overallProgress() * 100)}%` }}
              />
            </div>

            <div className="sheet-body">
              {title.media_type === 'movie' && (
                <div className="fact-row">
                  {title.release_date && (
                    <span className="fact">
                      <span aria-hidden>🗓</span> {formatDate(title.release_date)}
                    </span>
                  )}
                  <span className="fact">
                    <span aria-hidden>👁</span>{' '}
                    {movieWatched ? 'Watched' : 'Not watched'}
                  </span>
                  <button
                    className={`check-btn big${movieWatched ? ' done' : ''}`}
                    aria-label={movieWatched ? 'Watched' : 'Mark watched'}
                    disabled={busy || !!movieWatched}
                    onClick={markMovie}
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
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
              )}

              <div className="sheet-tabs">
                <button
                  className={tab === 'about' ? 'active' : ''}
                  onClick={() => setTab('about')}
                >
                  About
                </button>
                {title.media_type === 'tv' && (
                  <button
                    className={tab === 'episodes' ? 'active' : ''}
                    onClick={() => setTab('episodes')}
                  >
                    Episodes
                  </button>
                )}
              </div>

              {tab === 'about' && (
                <>
                  <h3>{title.media_type === 'movie' ? 'Movie info' : 'Show info'}</h3>
                  {title.vote_average != null && title.vote_average > 0 && (
                    <div className="rating-row">
                      <span className="rating-stars" aria-hidden>
                        {stars(title.vote_average)}
                      </span>
                      <span className="rating-num">
                        {(title.vote_average / 2).toFixed(1)}/5
                      </span>
                    </div>
                  )}
                  {title.tagline && (
                    <p className="tagline-text">“{title.tagline}”</p>
                  )}
                  {title.genres.length > 0 && (
                    <div className="genre-row">
                      {title.genres.map((g) => (
                        <span key={g} className="genre-pill">
                          {g}
                        </span>
                      ))}
                    </div>
                  )}
                  {title.overview && <p className="overview">{title.overview}</p>}
                  {title.trailer_url && (
                    <a
                      className="trailer-btn"
                      href={title.trailer_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      ▶ Watch trailer
                    </a>
                  )}
                  {title.cast.length > 0 && (
                    <>
                      <h3>Cast</h3>
                      <div className="cast-grid">
                        {title.cast.map((c) => (
                          <button
                            key={c.id}
                            type="button"
                            className="cast-card"
                            onClick={() => {
                              setPersonId(c.id)
                              setPersonName(c.name)
                            }}
                          >
                            {c.profile_url ? (
                              <img src={c.profile_url} alt="" />
                            ) : (
                              <div className="cast-ph">{c.name[0]}</div>
                            )}
                            <div className="cast-name">{c.name}</div>
                            {c.character && (
                              <div className="cast-role">{c.character}</div>
                            )}
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </>
              )}

              {tab === 'episodes' && title.media_type === 'tv' && (
                <div className="season-panel">
                  <div className="season-panel-head">
                    <h3>All episodes</h3>
                    <button
                      type="button"
                      className={`season-check${overallProgress() >= 1 ? ' done' : ''}`}
                      aria-label="Mark all episodes watched"
                      disabled={busy || overallProgress() >= 1}
                      onClick={onMarkAll}
                    >
                      <CheckIcon />
                    </button>
                  </div>

                  <div className="season-list">
                    {(title.seasons || []).map((s) => {
                      const isOpen = openSeason === s.season_number
                      const cached = episodesBySeason[s.season_number]
                      const label =
                        s.season_number === 0
                          ? s.name || 'Specials'
                          : s.name || `Season ${s.season_number}`
                      const { watched, total } = seasonProgress(
                        s.season_number,
                        s.episode_count,
                      )
                      const complete = total > 0 && watched >= total
                      const pct =
                        total > 0 ? Math.min(1, watched / total) : 0

                      return (
                        <div
                          key={s.season_number}
                          className={`season-card${isOpen ? ' is-open' : ''}`}
                        >
                          <div className="season-head">
                            <button
                              type="button"
                              className="season-toggle"
                              aria-expanded={isOpen}
                              onClick={() => toggleSeason(s.season_number)}
                            >
                              <span className="season-name">
                                {label}
                                <span className="season-caret" aria-hidden>
                                  {isOpen ? '▴' : '▾'}
                                </span>
                              </span>
                              <span className="season-count">
                                {watched}/{total || '–'}
                              </span>
                            </button>
                            <button
                              type="button"
                              className={`season-check${complete ? ' done' : ''}`}
                              aria-label={
                                complete
                                  ? `Unmark ${label}`
                                  : `Mark ${label} watched`
                              }
                              disabled={busy || total === 0}
                              onClick={() =>
                                onToggleSeason(s.season_number, complete)
                              }
                            >
                              <CheckIcon />
                            </button>
                          </div>
                          <div className="season-progress" aria-hidden>
                            <div
                              className={
                                complete
                                  ? 'fill full'
                                  : pct > 0
                                    ? 'fill partial'
                                    : 'fill'
                              }
                              style={{ width: `${Math.round(pct * 100)}%` }}
                            />
                          </div>

                          {isOpen && (
                            <div className="season-body">
                              {cached === 'loading' || cached == null ? (
                                <SeasonEpisodesSkeleton />
                              ) : cached.length === 0 ? (
                                <div className="empty">
                                  No episodes found for this season.
                                </div>
                              ) : (
                                <div className="episode-list">
                                  {cached.map((ep) => {
                                    const days = daysUntil(ep.air_date)
                                    const upcoming = days != null && days > 0
                                    const watched = isEpisodeWatched(
                                      ep.season,
                                      ep.episode,
                                    )
                                    return (
                                      <div
                                        key={`${ep.season}-${ep.episode}`}
                                        className="episode-row"
                                      >
                                        {ep.still_url ? (
                                          <img
                                            className="still"
                                            src={ep.still_url}
                                            alt=""
                                          />
                                        ) : (
                                          <div
                                            className={`still ph${upcoming ? ' film' : ''}`}
                                          />
                                        )}
                                        <div className="ep-info">
                                          <div className="ep-code">
                                            S
                                            {String(ep.season).padStart(2, '0')}{' '}
                                            | E
                                            {String(ep.episode).padStart(2, '0')}
                                          </div>
                                          <div className="ep-name">
                                            {ep.name ||
                                              (upcoming ? 'TBA' : 'Episode')}
                                          </div>
                                        </div>
                                        {upcoming ? (
                                          <div className="ep-countdown">
                                            <strong>{days}</strong>
                                            <span>days</span>
                                          </div>
                                        ) : (
                                          <button
                                            type="button"
                                            className={`season-check${watched ? ' done' : ''}`}
                                            aria-label={
                                              watched
                                                ? `Unmark episode ${ep.episode}`
                                                : `Mark episode ${ep.episode} watched`
                                            }
                                            disabled={busy}
                                            onClick={() => onToggleEpisode(ep)}
                                          >
                                            <CheckIcon />
                                          </button>
                                        )}
                                      </div>
                                    )
                                  })}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
              </>
            )}
            </div>

            {!(hydrating && !title.seasons && title.media_type === 'tv') && !item && (
              <button
                type="button"
                className="sheet-add-bar"
                onClick={add}
                disabled={busy || hydrating}
              >
                + Add {title.media_type === 'movie' ? 'movie' : 'show'}
              </button>
            )}
            {!(hydrating && !title.seasons && title.media_type === 'tv') && item && (
              <button
                type="button"
                className="sheet-remove-bar"
                onClick={remove}
                disabled={busy}
              >
                Remove from list
              </button>
            )}
          </>
        ) : (
          <DetailBodySkeleton />
        )}
      </div>

      {confirm && (
        <div className="dialog-backdrop">
          <div className="dialog" role="alertdialog">
            <h3>Mark earlier episodes too?</h3>
            <p>
              You marked S{confirm.season}E{confirm.episode}. There{' '}
              {confirm.previous === 1 ? 'is' : 'are'}{' '}
              <strong>{confirm.previous}</strong> earlier episode
              {confirm.previous === 1 ? '' : 's'} not marked yet.
            </p>
            <div className="dialog-actions">
              <button
                className="dialog-secondary"
                disabled={busy}
                onClick={() => doMarkEpisode(confirm.season, confirm.episode, false)}
              >
                Only this one
              </button>
              <button
                className="dialog-primary"
                disabled={busy}
                onClick={() => doMarkEpisode(confirm.season, confirm.episode, true)}
              >
                Mark all previous
              </button>
            </div>
            <button
              className="dialog-cancel"
              disabled={busy}
              onClick={() => setConfirm(null)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
      {personId != null && (
        <PersonSheet
          personId={personId}
          name={personName}
          onClose={() => setPersonId(null)}
          onOpenCredit={(result) => {
            setPersonId(null)
            onOpenSearch?.(result)
          }}
        />
      )}
    </>
  )
}
