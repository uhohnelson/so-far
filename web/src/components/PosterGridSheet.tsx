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
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </>
  )
}
