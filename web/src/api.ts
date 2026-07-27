import type {
  Episode,
  LibraryItem,
  MediaType,
  Person,
  SearchResult,
  Stats,
  TitleDetail,
  User,
  WatchStatus,
} from './types'

const TOKEN_KEY = 'sofar_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string>),
  }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`/api${path}`, { ...init, headers })
  if (res.status === 401 && !path.startsWith('/auth/')) {
    setToken(null)
    onUnauthorized?.()
    throw new ApiError(401, 'Signed out')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // keep statusText
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  exchangeCode: (code: string) =>
    request<{ token: string; user: User }>('/auth/exchange', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),

  logout: () => request<{ ok: boolean }>('/auth/logout', { method: 'POST' }),

  me: () => request<User>('/me'),

  updateMe: (body: { cover_title_id?: number | null; timezone?: string | null }) =>
    request<User>('/me', {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  stats: () => request<Stats>('/stats'),

  search: (q: string, mediaType?: MediaType) =>
    request<SearchResult[]>(
      `/search?q=${encodeURIComponent(q)}${
        mediaType ? `&media_type=${mediaType}` : ''
      }`,
    ),

  trending: (mediaType?: MediaType, limit = 20) =>
    request<SearchResult[]>(
      `/trending?limit=${limit}${mediaType ? `&media_type=${mediaType}` : ''}`,
    ),

  topRated: (mediaType: MediaType, limit = 20) =>
    request<SearchResult[]>(
      `/top-rated?media_type=${mediaType}&limit=${limit}`,
    ),

  personDetail: (personId: number) =>
    request<Person>(`/person/${personId}`),

  personCredits: (personId: number) =>
    request<SearchResult[]>(`/person/${personId}/credits`),

  titleDetail: (mediaType: MediaType, tmdbId: number) =>
    request<TitleDetail>(`/titles/${mediaType}/${tmdbId}`),

  similar: (mediaType: MediaType, tmdbId: number, limit = 12) =>
    request<SearchResult[]>(
      `/titles/${mediaType}/${tmdbId}/similar?limit=${limit}`,
    ),

  seasonEpisodes: (tmdbId: number, season: number) =>
    request<{ season: number; episodes: Episode[] }>(
      `/titles/tv/${tmdbId}/season/${season}`,
    ),

  library: (status?: WatchStatus) =>
    request<LibraryItem[]>(`/library${status ? `?status=${status}` : ''}`),

  addToLibrary: (body: {
    tmdb_id: number
    media_type: MediaType
    status?: WatchStatus
    current_season?: number
    current_episode?: number
  }) =>
    request<LibraryItem>('/library', {
      method: 'POST',
      body: JSON.stringify({ status: 'want', ...body }),
    }),

  removeFromLibrary: (id: number) =>
    request<{ ok: boolean }>(`/library/${id}`, { method: 'DELETE' }),

  setProgress: (id: number, season: number, episode: number) =>
    request<LibraryItem>(`/library/${id}/progress`, {
      method: 'POST',
      body: JSON.stringify({ season, episode }),
    }),

  markWatched: (id: number) =>
    request<{ message: string; item: LibraryItem }>(`/library/${id}/watched`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  previewMark: (id: number, season: number, episode: number) =>
    request<{ previous_unwatched: number }>(
      `/library/${id}/episodes/preview?season=${season}&episode=${episode}`,
    ),

  markEpisode: (
    id: number,
    season: number,
    episode: number,
    markPrevious: boolean,
  ) =>
    request<{
      message: string
      item: LibraryItem
      previous_unwatched: number
      previous_marked: number
    }>(`/library/${id}/episodes`, {
      method: 'POST',
      body: JSON.stringify({
        season,
        episode,
        mark_previous: markPrevious,
      }),
    }),

  unmarkEpisode: (id: number, season: number, episode: number) =>
    request<{ item: LibraryItem }>(
      `/library/${id}/episodes/${season}/${episode}`,
      { method: 'DELETE' },
    ),

  markSeason: (id: number, season: number) =>
    request<{ message: string; item: LibraryItem }>(
      `/library/${id}/seasons/${season}`,
      { method: 'POST', body: JSON.stringify({}) },
    ),

  unmarkSeason: (id: number, season: number) =>
    request<{ item: LibraryItem }>(`/library/${id}/seasons/${season}`, {
      method: 'DELETE',
    }),

  markAllSeasons: (id: number) =>
    request<{ message: string; item: LibraryItem }>(
      `/library/${id}/seasons/all`,
      { method: 'POST', body: JSON.stringify({}) },
    ),

  setAlertMuted: (id: number, muted: boolean) =>
    request<{ muted: boolean }>(`/library/${id}/alerts`, {
      method: 'PATCH',
      body: JSON.stringify({ muted }),
    }),
}
