export type MediaType = 'movie' | 'tv'
export type WatchStatus = 'want' | 'watching' | 'watched'

export interface SearchResult {
  tmdb_id: number
  media_type: MediaType
  title: string
  year: number | null
  overview: string | null
  poster_url: string | null
  backdrop_url: string | null
}

export interface Season {
  season_number: number
  episode_count: number | null
  name: string | null
  poster_url: string | null
  air_date: string | null
}

export interface CastMember {
  id: number
  name: string
  character: string | null
  profile_url: string | null
}

export interface Episode {
  season: number
  episode: number
  name: string | null
  air_date: string | null
  overview: string | null
  still_url: string | null
  runtime: number | null
  watched: boolean
}

export interface Provider {
  name: string
  logo_url: string | null
}

export interface Title {
  id: number
  tmdb_id: number
  media_type: MediaType
  title: string
  year: number | null
  overview: string | null
  poster_url: string | null
  backdrop_url: string | null
  tagline: string | null
  genres: string[]
  runtime: number | null
  status: string | null
  vote_average: number | null
  networks: string[]
  number_of_seasons: number | null
  number_of_episodes: number | null
  seasons: Season[] | null
  cast: CastMember[]
  release_date: string | null
  trailer_url: string | null
  providers: Provider[]
}

export interface LibraryItem {
  id: number
  status: WatchStatus
  current_season: number | null
  current_episode: number | null
  watched_count: number
  title: Title
}

export interface TitleDetail {
  title: Title
  library_item: LibraryItem | null
  watched_episodes: string[]
  alerts_muted?: boolean | null
}

export interface User {
  id: number
  display_name: string | null
  cover_title_id: number | null
  cover_url: string | null
  timezone: string | null
}

export interface Stats {
  episodes: number
  movies: number
  minutes: number
}

export interface Person {
  id: number
  name: string
  biography: string | null
  profile_url: string | null
  known_for: string | null
}
