import type { LibraryItem, SearchResult } from '../types'

type GridItem = SearchResult | LibraryItem

function isLibraryItem(item: GridItem): item is LibraryItem {
  return 'title' in item && typeof item.title === 'object'
}

function posterUrl(item: GridItem): string | null {
  if (isLibraryItem(item)) return item.title.poster_url
  return item.poster_url
}

function label(item: GridItem): string {
  if (isLibraryItem(item)) return item.title.title
  return item.title
}

function mediaTypeOf(item: GridItem): 'movie' | 'tv' {
  if (isLibraryItem(item)) return item.title.media_type
  return item.media_type
}

function totalEps(item: LibraryItem): number | null {
  const seasons = item.title.seasons
  if (!seasons) return null
  let total = 0
  for (const s of seasons) {
    if (s.season_number >= 1) total += s.episode_count ?? 0
  }
  return total || null
}

function progressOf(item: LibraryItem): number {
  if (item.title.media_type !== 'tv') return item.status === 'watched' ? 1 : 0
  if (item.status === 'watched') return 1
  const total = totalEps(item)
  if (!total) return 0
  const watched = item.watched_count ?? 0
  return Math.min(1, Math.max(0, watched / total))
}

interface PosterGridSheetProps {
  title: string
  items: GridItem[]
  onClose: () => void
  onOpen: (item: GridItem) => void
}

export default function PosterGridSheet({
  title,
  items,
  onClose,
  onOpen,
}: PosterGridSheetProps) {
  return (
    <>
      <div className="sheet-backdrop sheet-backdrop-high" onClick={onClose} />
      <div className="sheet grid-sheet" role="dialog" aria-label={title}>
        <div className="grid-sheet-head">
          <button className="icon-btn dark" onClick={onClose} aria-label="Close">
            ←
          </button>
          <h2>{title}</h2>
        </div>
        <div className="sheet-body">
          <div className="library-grid">
            {items.map((item) => {
              const key = isLibraryItem(item)
                ? `lib-${item.id}`
                : `${item.media_type}-${item.tmdb_id}`
              const showProgress =
                isLibraryItem(item) && mediaTypeOf(item) === 'tv'
              return (
                <button
                  key={key}
                  type="button"
                  className="grid-card"
                  onClick={() => onOpen(item)}
                >
                  {posterUrl(item) ? (
                    <img src={posterUrl(item)!} alt={label(item)} loading="lazy" />
                  ) : (
                    <div className="grid-ph">{label(item)}</div>
                  )}
                  {showProgress && (
                    <div className="grid-progress">
                      <div
                        className="grid-progress-fill"
                        style={{
                          width: `${Math.round(progressOf(item) * 100)}%`,
                        }}
                      />
                    </div>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </>
  )
}
