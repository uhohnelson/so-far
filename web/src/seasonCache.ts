import { api } from './api'
import type { Episode } from './types'

type SeasonKey = string

type CacheEntry =
  | { kind: 'ok'; episodes: Episode[] }
  | { kind: 'miss'; until: number }

/** Empty / failed season fetches are retried after this, not stored as success. */
const MISS_TTL_MS = 60_000

const cache = new Map<SeasonKey, CacheEntry>()
const inflight = new Map<SeasonKey, Promise<Episode[]>>()

function key(tmdbId: number, season: number): SeasonKey {
  return `${tmdbId}:${season}`
}

export function getCachedSeason(
  tmdbId: number,
  season: number,
): Episode[] | undefined {
  const entry = cache.get(key(tmdbId, season))
  if (entry?.kind === 'ok' && entry.episodes.length > 0) return entry.episodes
  return undefined
}

export function setCachedSeason(
  tmdbId: number,
  season: number,
  episodes: Episode[],
) {
  const k = key(tmdbId, season)
  if (episodes.length === 0) {
    cache.delete(k)
    return
  }
  cache.set(k, { kind: 'ok', episodes })
}

export function invalidateCachedSeason(tmdbId: number, season: number) {
  const k = key(tmdbId, season)
  cache.delete(k)
  inflight.delete(k)
}

function episodeKey(season: number, episode: number) {
  return `S${season}E${episode}`
}

/** Patch watched flags on every cached season for a show. */
export function patchCachedWatched(tmdbId: number, watchedKeys: string[]) {
  const prefix = `${tmdbId}:`
  for (const [k, entry] of cache.entries()) {
    if (!k.startsWith(prefix) || entry.kind !== 'ok') continue
    cache.set(k, {
      kind: 'ok',
      episodes: entry.episodes.map((ep) => ({
        ...ep,
        watched: watchedKeys.includes(episodeKey(ep.season, ep.episode)),
      })),
    })
  }
}

/** Run async work with a hard concurrency cap. */
export async function mapLimit<T, R>(
  items: T[],
  limit: number,
  fn: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  if (items.length === 0) return []
  const results = new Array<R>(items.length)
  let next = 0
  const workers = Array.from(
    { length: Math.min(limit, items.length) },
    async () => {
      while (true) {
        const i = next++
        if (i >= items.length) return
        results[i] = await fn(items[i], i)
      }
    },
  )
  await Promise.all(workers)
  return results
}

/** Deduped season fetch shared by WatchList + DetailSheet. */
export function loadSeasonEpisodes(
  tmdbId: number,
  season: number,
  opts?: { force?: boolean },
): Promise<Episode[]> {
  const k = key(tmdbId, season)
  if (!opts?.force) {
    const hit = cache.get(k)
    if (hit?.kind === 'ok' && hit.episodes.length > 0) {
      return Promise.resolve(hit.episodes)
    }
    if (hit?.kind === 'miss' && Date.now() < hit.until) {
      return Promise.resolve([])
    }
  } else {
    cache.delete(k)
  }

  const pending = inflight.get(k)
  if (pending) return pending

  const req = api
    .seasonEpisodes(tmdbId, season)
    .then((res) => {
      if (res.episodes.length > 0) {
        cache.set(k, { kind: 'ok', episodes: res.episodes })
      } else {
        cache.set(k, { kind: 'miss', until: Date.now() + MISS_TTL_MS })
      }
      inflight.delete(k)
      return res.episodes
    })
    .catch((err) => {
      inflight.delete(k)
      cache.set(k, { kind: 'miss', until: Date.now() + MISS_TTL_MS })
      throw err
    })

  inflight.set(k, req)
  return req
}

export function episodeName(
  tmdbId: number,
  season: number,
  episode: number,
): string | undefined {
  const eps = getCachedSeason(tmdbId, season)
  if (!eps) return undefined
  return eps.find((e) => e.episode === episode)?.name ?? ''
}
