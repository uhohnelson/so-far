import { api } from './api'
import type { Episode } from './types'

type SeasonKey = string

const cache = new Map<SeasonKey, Episode[]>()
const inflight = new Map<SeasonKey, Promise<Episode[]>>()

function key(tmdbId: number, season: number): SeasonKey {
  return `${tmdbId}:${season}`
}

export function getCachedSeason(
  tmdbId: number,
  season: number,
): Episode[] | undefined {
  return cache.get(key(tmdbId, season))
}

export function setCachedSeason(
  tmdbId: number,
  season: number,
  episodes: Episode[],
) {
  cache.set(key(tmdbId, season), episodes)
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
): Promise<Episode[]> {
  const k = key(tmdbId, season)
  const hit = cache.get(k)
  if (hit) return Promise.resolve(hit)

  const pending = inflight.get(k)
  if (pending) return pending

  const req = api
    .seasonEpisodes(tmdbId, season)
    .then((res) => {
      cache.set(k, res.episodes)
      inflight.delete(k)
      return res.episodes
    })
    .catch((err) => {
      inflight.delete(k)
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
  const eps = cache.get(key(tmdbId, season))
  if (!eps) return undefined
  return eps.find((e) => e.episode === episode)?.name ?? ''
}
