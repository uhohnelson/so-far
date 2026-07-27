import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { MediaType, SearchResult } from '../types'
import PosterGridSheet from './PosterGridSheet'
import { SearchSkeleton, ShelfSkeleton } from './Skeletons'

interface DiscoverProps {
  onOpen: (result: SearchResult) => void
  onQuickAdd: (result: SearchResult) => void
  isAdded: (result: SearchResult) => boolean
}

type DiscoverFilter = 'all' | MediaType

type GridView = {
  title: string
  items: SearchResult[]
}

function PosterCard({
  item,
  added,
  onOpen,
  onQuickAdd,
}: {
  item: SearchResult
  added: boolean
  onOpen: () => void
  onQuickAdd: () => void
}) {
  return (
    <div className={`poster-card${added ? ' added' : ''}`}>
      <button type="button" className="poster-hit" onClick={onOpen}>
        {item.poster_url ? (
          <img className="art" src={item.poster_url} alt={item.title} loading="lazy" />
        ) : (
          <div className="art ph">🎬</div>
        )}
        <div className="caption">{item.title}</div>
      </button>
      {added ? (
        <span className="added-badge" title="On your list">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M5 13l4 4L19 7"
              stroke="currentColor"
              strokeWidth="3.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="sr-only">On your list</span>
        </span>
      ) : (
        <button
          type="button"
          className="plus"
          aria-label={`Add ${item.title}`}
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            onQuickAdd()
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden>
            <path
              d="M7 1v12M1 7h12"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
            />
          </svg>
        </button>
      )}
    </div>
  )
}

export default function Discover({
  onOpen,
  onQuickAdd,
  isAdded,
}: DiscoverProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [filter, setFilter] = useState<DiscoverFilter>('all')
  const [trendingMovies, setTrendingMovies] = useState<SearchResult[] | null>(
    null,
  )
  const [topMovies, setTopMovies] = useState<SearchResult[] | null>(null)
  const [trendingTv, setTrendingTv] = useState<SearchResult[] | null>(null)
  const [topTv, setTopTv] = useState<SearchResult[] | null>(null)
  const [gridView, setGridView] = useState<GridView | null>(null)
  const [loading, setLoading] = useState(false)
  const debounce = useRef<number | undefined>(undefined)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [movieTrending, movieTop, tvTrending, tvTop] = await Promise.all([
          api.trending('movie'),
          api.topRated('movie'),
          api.trending('tv'),
          api.topRated('tv'),
        ])
        if (!cancelled) {
          setTrendingMovies(movieTrending)
          setTopMovies(movieTop)
          setTrendingTv(tvTrending)
          setTopTv(tvTop)
        }
      } catch {
        if (!cancelled) {
          setTrendingMovies([])
          setTopMovies([])
          setTrendingTv([])
          setTopTv([])
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    window.clearTimeout(debounce.current)
    const q = query.trim()
    if (q.length < 2) {
      setResults(null)
      setLoading(false)
      return
    }
    setLoading(true)
    debounce.current = window.setTimeout(async () => {
      try {
        setResults(await api.search(q, filter === 'all' ? undefined : filter))
      } catch {
        setResults([])
      } finally {
        setLoading(false)
      }
    }, 320)
    return () => window.clearTimeout(debounce.current)
  }, [query, filter])

  const searching = query.trim().length >= 2
  const showMovies = filter === 'all' || filter === 'movie'
  const showTv = filter === 'all' || filter === 'tv'

  const openShelfGrid = async (
    title: string,
    items: SearchResult[] | null,
    loader: () => Promise<SearchResult[]>,
  ) => {
    if (items?.length) {
      setGridView({ title, items })
      return
    }
    try {
      const loaded = await loader()
      setGridView({ title, items: loaded })
    } catch {
      setGridView({ title, items: [] })
    }
  }

  const shelf = (
    title: string,
    subtitle: string,
    items: SearchResult[] | null,
    keyPrefix: string,
    onSeeMore: () => void,
  ) => (
    <section className="discover-shelf">
      <div className="section-label">
        {title}
        <button type="button" className="see-all" onClick={onSeeMore}>
          See more
        </button>
      </div>
      <div className="section-sub">{subtitle}</div>
      {items === null ? (
        <div aria-label={`Loading ${title}`}>
          <ShelfSkeleton />
        </div>
      ) : items.length === 0 ? (
        <div className="shelf-empty">Nothing available right now.</div>
      ) : (
        <div className="poster-row">
          {items.slice(0, 12).map((r) => (
            <PosterCard
              key={`${keyPrefix}-${r.media_type}-${r.tmdb_id}`}
              item={r}
              added={isAdded(r)}
              onOpen={() => onOpen(r)}
              onQuickAdd={() => onQuickAdd(r)}
            />
          ))}
        </div>
      )}
    </section>
  )

  return (
    <div className="page">
      <div className="search-bar">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <input
          ref={searchRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search shows and movies"
        />
      </div>

      <div className="discover-filters" aria-label="Filter discover results">
        {(
          [
            ['all', 'All'],
            ['movie', 'Movies'],
            ['tv', 'TV shows'],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={filter === value ? 'active' : ''}
            aria-pressed={filter === value}
            onClick={() => setFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>

      {searching ? (
        <>
          {loading && <SearchSkeleton />}
          {!loading && results?.length === 0 && (
            <div className="empty">No results for “{query.trim()}”.</div>
          )}
          {!loading && results && results.length > 0 && (
            <>
              <div className="section-label">Results</div>
              <div className="poster-row" style={{ flexWrap: 'wrap' }}>
                {results.map((r) => (
                  <PosterCard
                    key={`${r.media_type}-${r.tmdb_id}`}
                    item={r}
                    added={isAdded(r)}
                    onOpen={() => onOpen(r)}
                    onQuickAdd={() => onQuickAdd(r)}
                  />
                ))}
              </div>
            </>
          )}
        </>
      ) : (
        <>
          {showMovies &&
            shelf(
              'Trending movies',
              'THIS WEEK',
              trendingMovies,
              'tm',
              () =>
                openShelfGrid('Trending movies', trendingMovies, () =>
                  api.trending('movie'),
                ),
            )}
          {showMovies &&
            shelf('Top movies', 'TOP RATED', topMovies, 'topm', () =>
              openShelfGrid('Top movies', topMovies, () =>
                api.topRated('movie'),
              ),
            )}
          {showTv &&
            shelf(
              'Trending TV shows',
              'THIS WEEK',
              trendingTv,
              'ttv',
              () =>
                openShelfGrid('Trending TV shows', trendingTv, () =>
                  api.trending('tv'),
                ),
            )}
          {showTv &&
            shelf('Top TV shows', 'TOP RATED', topTv, 'toptv', () =>
              openShelfGrid('Top TV shows', topTv, () => api.topRated('tv')),
            )}

          <button
            className="browse-cta"
            onClick={() => searchRef.current?.focus()}
          >
            Search movies and TV shows ›
          </button>
        </>
      )}

      {gridView && (
        <PosterGridSheet
          title={gridView.title}
          items={gridView.items}
          onClose={() => setGridView(null)}
          onOpen={(item) => {
            setGridView(null)
            onOpen(item as SearchResult)
          }}
        />
      )}
    </div>
  )
}
