import { useMatch } from '../lib/context'
import { clockLabel } from '../lib/match'
import { useFrame } from '../lib/playback'
import { t } from '../lib/profile'
import { usePresence } from '../lib/usePresence'
import type { Lang, Overlay } from '../types'

export function Scorebug({ lang, overlay }: { lang: Lang; overlay?: Overlay }) {
  const { m, pb } = useMatch()
  const frame = useFrame(pb)
  const { home, away } = m.bundle.match
  const score = m.bundle.frames.score[Math.min(frame, m.bundle.frames.score.length - 1)] ?? [0, 0]
  const { shown, leaving } = usePresence(overlay)
  const share = Number(shown?.payload.home_share ?? 0.5)

  return (
    <div className="scorebug">
      <div className="sb-main">
        <div className="sb-live">
          <span className="dot" />
          {t(lang, 'live')}
        </div>
        <Side club={home} />
        <div className="sb-score">
          <span key={`h${score[0]}`} className="sb-num">{score[0]}</span>
          <span className="sb-sep">–</span>
          <span key={`a${score[1]}`} className="sb-num">{score[1]}</span>
        </div>
        <Side club={away} right />
        <div className="sb-clock">{clockLabel(m.bundle, frame)}</div>
      </div>
      {shown && (
        <div className={`sb-extra ${leaving ? 'leave' : 'enter'}`}>
          <div className="sb-extra-text">
            <b>{shown.headline}</b> {shown.body}
          </div>
          {shown.type === 'momentum' && (
            <div className="sb-momentum">
              <i style={{ width: `${share * 100}%`, background: home.color }} />
              <i style={{ width: `${(1 - share) * 100}%`, background: away.color }} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Side({ club, right }: { club: { short: string; color: string }; right?: boolean }) {
  return (
    <div className={`sb-team ${right ? 'right' : ''}`}>
      <i className="sb-chip" style={{ background: club.color }} />
      <span>{club.short}</span>
    </div>
  )
}
