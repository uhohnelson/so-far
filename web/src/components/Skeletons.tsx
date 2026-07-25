export function WatchListSkeleton() {
  return (
    <>
      <div className="tabs">
        <span className="skel skel-tab" />
        <span className="skel skel-tab short" />
      </div>
      <div className="page" aria-busy="true" aria-label="Loading watch list">
        <div className="skel skel-cta" />
        <div className="ep-list">
          {Array.from({ length: 6 }, (_, i) => (
            <div className="skel-ep-card" key={i}>
              <div className="skel skel-thumb" />
              <div className="skel-ep-lines">
                <div className="skel skel-line w60" />
                <div className="skel skel-line w40" />
                <div className="skel skel-line w80" />
              </div>
              <div className="skel skel-check" />
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

export function ShelfSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="poster-row skel-poster-row" aria-hidden>
      {Array.from({ length: count }, (_, i) => (
        <div className="skel-poster" key={i}>
          <div className="skel skel-poster-art" />
          <div className="skel skel-line" />
        </div>
      ))}
    </div>
  )
}

export function SearchSkeleton() {
  return (
    <div className="poster-row skel-search-grid" aria-busy="true" aria-label="Searching">
      {Array.from({ length: 8 }, (_, i) => (
        <div className="skel-poster" key={i}>
          <div className="skel skel-poster-art" />
          <div className="skel skel-line" />
        </div>
      ))}
    </div>
  )
}

export function DetailBodySkeleton() {
  return (
    <div className="sheet-body" aria-busy="true" aria-label="Loading details">
      <div className="skel skel-line w40" style={{ marginBottom: 16 }} />
      <div className="skel skel-block" />
      <div className="skel skel-line" style={{ marginTop: 16 }} />
      <div className="skel skel-line w80" style={{ marginTop: 8 }} />
      <div className="skel skel-line w60" style={{ marginTop: 8 }} />
    </div>
  )
}

export function SeasonEpisodesSkeleton() {
  return (
    <div className="skel-season-eps" aria-busy="true">
      {Array.from({ length: 5 }, (_, i) => (
        <div className="skel-ep-row" key={i}>
          <div className="skel skel-still" />
          <div className="skel-ep-lines">
            <div className="skel skel-line w50" />
            <div className="skel skel-line w80" />
          </div>
        </div>
      ))}
    </div>
  )
}
