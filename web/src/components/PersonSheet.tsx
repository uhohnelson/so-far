import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Person, SearchResult } from '../types'

interface PersonSheetProps {
  personId: number
  name: string
  onClose: () => void
  onOpenCredit: (result: SearchResult) => void
}

export default function PersonSheet({
  personId,
  name,
  onClose,
  onOpenCredit,
}: PersonSheetProps) {
  const [person, setPerson] = useState<Person | null>(null)
  const [credits, setCredits] = useState<SearchResult[] | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [detail, filmography] = await Promise.all([
          api.personDetail(personId),
          api.personCredits(personId),
        ])
        if (!cancelled) {
          setPerson(detail)
          setCredits(filmography)
        }
      } catch {
        if (!cancelled) {
          setPerson({
            id: personId,
            name,
            biography: null,
            profile_url: null,
            known_for: null,
          })
          setCredits([])
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [personId, name])

  const displayName = person?.name || name

  return (
    <>
      <div className="sheet-backdrop sheet-backdrop-high" onClick={onClose} />
      <div className="sheet person-sheet" role="dialog" aria-label={displayName}>
        <div className="person-head">
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ←
          </button>
          <div className="person-hero">
            {person?.profile_url ? (
              <img src={person.profile_url} alt="" />
            ) : (
              <div className="person-ph">{displayName[0]}</div>
            )}
            <div>
              <h2>{displayName}</h2>
              {person?.known_for && (
                <div className="person-known">{person.known_for}</div>
              )}
            </div>
          </div>
        </div>
        <div className="sheet-body">
          {person?.biography && (
            <p className="overview person-bio">{person.biography}</p>
          )}
          <h3>Filmography</h3>
          {credits === null ? (
            <div className="shelf-empty">Loading credits…</div>
          ) : credits.length === 0 ? (
            <div className="shelf-empty">No credits found.</div>
          ) : (
            <div className="library-grid person-grid">
              {credits.map((item) => (
                <button
                  key={`${item.media_type}-${item.tmdb_id}`}
                  type="button"
                  className="grid-card"
                  onClick={() => onOpenCredit(item)}
                >
                  {item.poster_url ? (
                    <img src={item.poster_url} alt={item.title} loading="lazy" />
                  ) : (
                    <div className="grid-ph">{item.title}</div>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
