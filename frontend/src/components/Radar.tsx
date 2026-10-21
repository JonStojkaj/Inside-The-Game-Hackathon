import { useEffect, useRef } from 'react'
import { useMatch } from '../lib/context'
import { frameAt, PITCH_L, PITCH_W } from '../lib/match'

/**
 * Our own mini radar for the TV view, drawn from the tracking data. It sits exactly on top of the
 * engine's minimap (bottom-centre of the GRF render), so the picture carries only our graphics.
 */
export function Radar({ focusPlayer }: { focusPlayer?: string | null }) {
  const { m, pb } = useMatch()
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current!
    const ctx = canvas.getContext('2d')!
    const { bundle } = m
    const players = bundle.match.players
    const colors = { home: bundle.match.home.color, away: bundle.match.away.color }
    const focus = focusPlayer ? m.playerIdx.get(focusPlayer) : undefined
    let raf = 0

    const draw = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      if (canvas.width !== Math.round(w * dpr)) canvas.width = Math.round(w * dpr)
      if (canvas.height !== Math.round(h * dpr)) canvas.height = Math.round(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)
      const pad = Math.max(4, w * 0.05)
      const s = Math.min((w - 2 * pad) / PITCH_L, (h - 2 * pad) / PITCH_W)
      const ox = (w - PITCH_L * s) / 2
      const oy = (h - PITCH_W * s) / 2
      const X = (x: number) => ox + x * s
      const Y = (y: number) => oy + (PITCH_W - y) * s

      ctx.strokeStyle = 'rgba(255,255,255,0.35)'
      ctx.lineWidth = 1
      ctx.strokeRect(X(0), Y(PITCH_W), PITCH_L * s, PITCH_W * s)
      ctx.beginPath()
      ctx.moveTo(X(52.5), Y(0))
      ctx.lineTo(X(52.5), Y(PITCH_W))
      ctx.stroke()
      ctx.beginPath()
      ctx.arc(X(52.5), Y(34), 9.15 * s, 0, Math.PI * 2)
      ctx.stroke()
      ctx.strokeRect(X(0), Y(54.16), 16.5 * s, 40.32 * s)
      ctx.strokeRect(X(PITCH_L - 16.5), Y(54.16), 16.5 * s, 40.32 * s)

      const fv = frameAt(bundle, pb.frame)
      const r = Math.max(2.2, s * 1.4)
      fv.players.forEach((q, i) => {
        ctx.fillStyle = colors[players[i].team]
        ctx.beginPath()
        ctx.arc(X(q[0]), Y(q[1]), i === focus ? r * 1.5 : r, 0, Math.PI * 2)
        ctx.fill()
        ctx.strokeStyle = i === focus ? '#ffc83d' : 'rgba(255,255,255,0.85)'
        ctx.lineWidth = i === focus ? 2 : 1
        ctx.stroke()
      })
      ctx.fillStyle = '#fff'
      ctx.beginPath()
      ctx.arc(X(fv.ball[0]), Y(fv.ball[1]), r * 0.8, 0, Math.PI * 2)
      ctx.fill()
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [m, pb, focusPlayer])

  return (
    <div className="tv-cover tv-radar">
      <canvas ref={ref} />
    </div>
  )
}
