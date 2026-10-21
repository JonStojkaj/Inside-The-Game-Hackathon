import { useEffect, useRef } from 'react'
import { useMatch } from '../lib/context'
import { frameAt, PITCH_L, PITCH_W } from '../lib/match'
import type { XY } from '../types'

type Ghosts = { ghost_paths: XY[][]; alt_ghost_paths: XY[][] }

export interface PitchTag {
  playerId: string
  label: string
  since: number // performance.now() when it appeared, for the enter animation
}

export interface PitchProps {
  /** Freeze on this frame (Sliding Doors) instead of following the clock. */
  frozenFrame?: number | null
  ghosts?: { insight: Ghosts; since: number } | null
  tags?: PitchTag[]
  focusPlayer?: string | null
  /** Camera follows the focus player (player-focus mode) instead of showing the whole pitch. */
  follow?: boolean
  showPressure?: boolean
  /** Draw only players/ball/ghosts on a transparent background (TV view). */
  transparent?: boolean
}

const ALT = '#ffc83d'
const REAL = '#ffffff'
const GHOST_MS = 2600

interface View {
  cx: number
  cy: number
  span: number // metres of pitch length visible
}
const FULL_VIEW: View = { cx: PITCH_L / 2, cy: PITCH_W / 2, span: PITCH_L }
const views = new WeakMap<Ghosts, View>()

/** Frame the ghost futures (plus margin), keeping the lower part of the screen free for the card. */
function ghostView(ins: Ghosts): View {
  const pts = [...ins.ghost_paths, ...ins.alt_ghost_paths].flat()
  if (!pts.length) return FULL_VIEW
  // 5-95 % of the points: a few stray futures must not zoom the camera out
  const q = (v: number[], p: number) => v.sort((a, b) => a - b)[Math.floor(p * (v.length - 1))]
  const xs = pts.map((pt) => pt[0])
  const ys = pts.map((pt) => pt[1])
  const [x0, x1, y0, y1] = [q(xs, 0.05), q(xs, 0.95), q(ys, 0.05), q(ys, 0.95)]
  const span = Math.min(PITCH_L, Math.max(45, (x1 - x0) * 1.6, (y1 - y0) * 1.6 * (PITCH_L / PITCH_W)))
  const half = span / 2
  const cx = Math.min(Math.max((x0 + x1) / 2, half - 3), PITCH_L - half + 3)
  return { cx, cy: (y0 + y1) / 2 - span * 0.1, span }
}

const FOLLOW_SPAN = 50
/** Broadcast "player cam": about half the pitch, centred on the player, kept inside the pitch. */
function followView([x, y]: XY): View {
  const half = FOLLOW_SPAN / 2
  return { cx: Math.min(Math.max(x, half - 4), PITCH_L - half + 4), cy: Math.min(Math.max(y, 18), PITCH_W - 18), span: FOLLOW_SPAN }
}

const easeOut = (t: number) => 1 - Math.pow(1 - Math.min(Math.max(t, 0), 1), 3)

function shade(hex: string, k: number): string {
  const n = parseInt(hex.slice(1), 16)
  const c = (v: number) => Math.round(Math.min(255, Math.max(0, v * k)))
  return `rgb(${c((n >> 16) & 255)},${c((n >> 8) & 255)},${c(n & 255)})`
}

/** 2D tactical pitch on a canvas, redrawn every animation frame from the shared clock. */
export function Pitch(props: PitchProps) {
  const { m, pb } = useMatch()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const propsRef = useRef(props)
  useEffect(() => {
    propsRef.current = props
  })

  useEffect(() => {
    const canvas = canvasRef.current!
    const ctx = canvas.getContext('2d')!
    const { bundle } = m
    const players = bundle.match.players
    const colors = { home: bundle.match.home.color, away: bundle.match.away.color }
    let raf = 0
    let w = 0
    let h = 0
    let dpr = 1
    let cam: View | null = null
    let lastNow = performance.now()

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      w = canvas.clientWidth
      h = canvas.clientHeight
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
    }
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)
    resize()

    const draw = (now: number) => {
      const p = propsRef.current
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)

      // camera: whole pitch, zoomed onto the ghost futures during Sliding Doors, or following the
      // focus player
      const fi = p.follow && p.focusPlayer ? m.playerIdx.get(p.focusPlayer) : undefined
      const target = p.ghosts
        ? (views.get(p.ghosts.insight) ?? views.set(p.ghosts.insight, ghostView(p.ghosts.insight)).get(p.ghosts.insight)!)
        : fi != null
          ? followView(frameAt(bundle, p.frozenFrame ?? pb.frame).players[fi])
          : FULL_VIEW
      if (!cam) cam = { ...target }
      const k = 1 - Math.exp(-Math.min(now - lastNow, 100) / 380)
      lastNow = now
      cam.cx += (target.cx - cam.cx) * k
      cam.cy += (target.cy - cam.cy) * k
      cam.span += (target.span - cam.span) * k
      // leave room for scorebug (top) and ticker (bottom); tall stages keep the lower half for graphics
      const tall = h > w * 0.8
      const s = Math.min((w * (tall ? 0.94 : 0.88)) / cam.span, (h * (tall ? 0.5 : 0.78)) / ((cam.span * PITCH_W) / PITCH_L))
      const ox = w / 2 - cam.cx * s
      const oy = h * (tall ? 0.36 : 0.49) - (PITCH_W - cam.cy) * s
      const X = (x: number) => ox + x * s
      const Y = (y: number) => oy + (PITCH_W - y) * s

      if (!p.transparent) drawPitch(ctx, w, h, s, X, Y)

      const frozen = p.frozenFrame != null
      const f = frozen ? p.frozenFrame! : pb.frame
      const fv = frameAt(bundle, f)

      // ball trail (last second)
      if (!frozen) {
        ctx.lineCap = 'round'
        for (let k = 1; k <= 10; k++) {
          const a = frameAt(bundle, Math.max(0, f - k)).ball
          const b = frameAt(bundle, Math.max(0, f - k + 1)).ball
          ctx.strokeStyle = `rgba(255,255,255,${0.16 * (1 - k / 10)})`
          ctx.lineWidth = Math.max(1, s * 0.35)
          ctx.beginPath()
          ctx.moveTo(X(a[0]), Y(a[1]))
          ctx.lineTo(X(b[0]), Y(b[1]))
          ctx.stroke()
        }
      }

      const r = Math.max(6, Math.min(s * 1.25, h * 0.021))
      const owner = fv.owner

      // pressure halo around the ball carrier (analyst)
      if (p.showPressure && owner >= 0 && !frozen) {
        const op = fv.players[owner]
        const team = players[owner].team
        let pressure = 0
        fv.players.forEach((q, i) => {
          if (players[i].team !== team) pressure += Math.max(0, 1 - Math.hypot(q[0] - op[0], q[1] - op[1]) / 5)
        })
        const g = ctx.createRadialGradient(X(op[0]), Y(op[1]), r, X(op[0]), Y(op[1]), 5 * s)
        g.addColorStop(0, `rgba(255,70,70,${Math.min(0.45, 0.12 + pressure * 0.22)})`)
        g.addColorStop(1, 'rgba(255,70,70,0)')
        ctx.fillStyle = g
        ctx.beginPath()
        ctx.arc(X(op[0]), Y(op[1]), 5 * s, 0, Math.PI * 2)
        ctx.fill()
        ctx.setLineDash([3, 4])
        ctx.strokeStyle = 'rgba(255,120,120,0.45)'
        ctx.lineWidth = 1
        ctx.stroke()
        ctx.setLineDash([])
      }

      // ghosts: real futures first, then the alternative fanning out on top
      if (p.ghosts) {
        const el = now - p.ghosts.since
        drawGhosts(ctx, p.ghosts.insight.ghost_paths, REAL, 0.2, easeOut(el / GHOST_MS), X, Y, s)
        drawGhosts(ctx, p.ghosts.insight.alt_ghost_paths, ALT, 0.6, easeOut((el - GHOST_MS * 0.55) / GHOST_MS), X, Y, s)
      }

      // players
      ctx.globalAlpha = frozen ? 0.7 : 1
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      fv.players.forEach((q, i) => {
        const pl = players[i]
        const cx = X(q[0])
        const cy = Y(q[1])
        const base = colors[pl.team]
        const gk = pl.position === 'GK'
        ctx.fillStyle = 'rgba(0,0,0,0.35)'
        ctx.beginPath()
        ctx.ellipse(cx + r * 0.18, cy + r * 0.32, r * 1.02, r * 0.8, 0, 0, Math.PI * 2)
        ctx.fill()
        if (i === owner) {
          const pulse = 0.5 + 0.5 * Math.sin(now / 220)
          ctx.strokeStyle = `rgba(255,255,255,${0.55 + 0.35 * pulse})`
          ctx.lineWidth = Math.max(1.5, r * 0.2)
          ctx.beginPath()
          ctx.arc(cx, cy, r * (1.55 + 0.12 * pulse), 0, Math.PI * 2)
          ctx.stroke()
        }
        if (p.focusPlayer === pl.id) {
          ctx.strokeStyle = ALT
          ctx.lineWidth = Math.max(2, r * 0.22)
          ctx.beginPath()
          ctx.arc(cx, cy, r * 1.35, 0, Math.PI * 2)
          ctx.stroke()
        }
        const grad = ctx.createLinearGradient(cx, cy - r, cx, cy + r)
        grad.addColorStop(0, shade(base, gk ? 0.75 : 1.25))
        grad.addColorStop(1, shade(base, gk ? 0.45 : 0.8))
        ctx.fillStyle = grad
        ctx.beginPath()
        ctx.arc(cx, cy, r, 0, Math.PI * 2)
        ctx.fill()
        ctx.strokeStyle = gk ? ALT : 'rgba(255,255,255,0.9)'
        ctx.lineWidth = Math.max(1, r * 0.14)
        ctx.stroke()
        ctx.fillStyle = '#fff'
        ctx.font = `700 ${Math.round(r * 1.12)}px "Barlow Condensed", sans-serif`
        ctx.fillText(String(pl.number), cx, cy + r * 0.06)
      })
      ctx.globalAlpha = 1

      // tags (player_tag overlays + focus player)
      const tags = [...(p.tags ?? [])]
      if (p.focusPlayer && !tags.some((t) => t.playerId === p.focusPlayer)) {
        const fp = m.player(p.focusPlayer)
        if (fp) tags.push({ playerId: fp.id, label: fp.name.split(' ').slice(-1)[0].toUpperCase(), since: 0 })
      }
      for (const tag of tags) {
        const i = m.playerIdx.get(tag.playerId)
        if (i == null) continue
        const q = fv.players[i]
        const a = easeOut((now - tag.since) / 350)
        drawTag(ctx, tag.label, X(q[0]), Y(q[1]) - r * 1.9 - (1 - a) * 8, r, colors[players[i].team], a)
      }

      // ball: lifts and grows with height, shadow stays on the ground
      const [bx, by, bz] = fv.ball
      const br = Math.max(3.5, s * 0.55) * (1 + Math.min(bz, 8) * 0.06)
      ctx.fillStyle = 'rgba(0,0,0,0.45)'
      ctx.beginPath()
      ctx.ellipse(X(bx) + bz * s * 0.25, Y(by) + bz * s * 0.15 + br * 0.4, br, br * 0.7, 0, 0, Math.PI * 2)
      ctx.fill()
      const bg = ctx.createRadialGradient(X(bx) - br * 0.35, Y(by) - bz * s * 0.3 - br * 0.35, br * 0.1, X(bx), Y(by) - bz * s * 0.3, br)
      bg.addColorStop(0, '#ffffff')
      bg.addColorStop(1, '#c9d2dc')
      ctx.fillStyle = bg
      ctx.beginPath()
      ctx.arc(X(bx), Y(by) - bz * s * 0.3, br, 0, Math.PI * 2)
      ctx.fill()
      ctx.strokeStyle = 'rgba(0,0,0,0.5)'
      ctx.lineWidth = 1
      ctx.stroke()
      if (p.ghosts) drawDecision(ctx, X(bx), Y(by) - bz * s * 0.3, br * 2.2, now)

      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
    }
  }, [m, pb])

  return <canvas ref={canvasRef} className="pitch-canvas" />
}

function drawPitch(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  s: number,
  X: (x: number) => number,
  Y: (y: number) => number,
) {
  const bg = ctx.createRadialGradient(w / 2, h / 2, h * 0.1, w / 2, h / 2, w * 0.75)
  bg.addColorStop(0, '#0f2219')
  bg.addColorStop(1, '#05090a')
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, w, h)

  // mowing stripes
  const stripes = 14
  for (let k = 0; k < stripes; k++) {
    ctx.fillStyle = k % 2 ? '#17432e' : '#1a4b33'
    ctx.fillRect(X((PITCH_L / stripes) * k), Y(PITCH_W), (PITCH_L / stripes) * s + 0.5, PITCH_W * s)
  }
  // vignette on the grass
  const vg = ctx.createRadialGradient(X(52.5), Y(34), s * 20, X(52.5), Y(34), s * 70)
  vg.addColorStop(0, 'rgba(0,0,0,0)')
  vg.addColorStop(1, 'rgba(0,0,0,0.35)')
  ctx.fillStyle = vg
  ctx.fillRect(X(0), Y(PITCH_W), PITCH_L * s, PITCH_W * s)

  ctx.strokeStyle = 'rgba(255,255,255,0.62)'
  ctx.lineWidth = Math.max(1, s * 0.14)
  const rect = (x0: number, y0: number, x1: number, y1: number) => ctx.strokeRect(X(x0), Y(y1), (x1 - x0) * s, (y1 - y0) * s)
  rect(0, 0, PITCH_L, PITCH_W)
  ctx.beginPath()
  ctx.moveTo(X(52.5), Y(0))
  ctx.lineTo(X(52.5), Y(PITCH_W))
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(X(52.5), Y(34), 9.15 * s, 0, Math.PI * 2)
  ctx.stroke()
  for (const side of [0, 1]) {
    const gx = side ? PITCH_L : 0
    const d = side ? -1 : 1
    rect(Math.min(gx, gx + d * 16.5), 34 - 20.16, Math.max(gx, gx + d * 16.5), 34 + 20.16)
    rect(Math.min(gx, gx + d * 5.5), 34 - 9.16, Math.max(gx, gx + d * 5.5), 34 + 9.16)
    ctx.beginPath()
    const a0 = Math.acos(5.5 / 9.15)
    const start = side ? Math.PI - a0 : -a0
    ctx.arc(X(gx + d * 11), Y(34), 9.15 * s, start, start + 2 * a0)
    ctx.stroke()
    ctx.fillStyle = 'rgba(255,255,255,0.7)'
    ctx.beginPath()
    ctx.arc(X(gx + d * 11), Y(34), Math.max(1.2, s * 0.22), 0, Math.PI * 2)
    ctx.fill()
    // goal frame
    ctx.fillStyle = 'rgba(255,255,255,0.12)'
    ctx.fillRect(X(side ? PITCH_L : -2), Y(34 + 3.66), 2 * s, 7.32 * s)
    ctx.strokeRect(X(side ? PITCH_L : -2), Y(34 + 3.66), 2 * s, 7.32 * s)
  }
  ctx.fillStyle = 'rgba(255,255,255,0.7)'
  ctx.beginPath()
  ctx.arc(X(52.5), Y(34), Math.max(1.2, s * 0.22), 0, Math.PI * 2)
  ctx.fill()
}

function drawGhosts(
  ctx: CanvasRenderingContext2D,
  paths: XY[][],
  color: string,
  alpha: number,
  progress: number,
  X: (x: number) => number,
  Y: (y: number) => number,
  s: number,
) {
  if (progress <= 0 || !paths.length) return
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.strokeStyle = color
  ctx.fillStyle = color
  ctx.shadowColor = color
  for (const full of paths) {
    const path = untilRestart(full)
    if (path.length < 2) continue
    // the visible part of the path, then drawn smoothed through segment midpoints
    const upto = progress * (path.length - 1)
    const n = Math.floor(upto)
    const pts: [number, number][] = path.slice(0, n + 1).map((q) => [X(q[0]), Y(q[1])])
    if (n + 1 < path.length) {
      const f = upto - n
      pts.push([X(path[n][0] + (path[n + 1][0] - path[n][0]) * f), Y(path[n][1] + (path[n + 1][1] - path[n][1]) * f)])
    }
    ctx.globalAlpha = alpha
    ctx.shadowBlur = 0
    ctx.lineWidth = Math.max(1.3, Math.min(s * 0.24, 2.4))
    ctx.beginPath()
    ctx.moveTo(pts[0][0], pts[0][1])
    for (let k = 1; k < pts.length - 1; k++) {
      const mx = (pts[k][0] + pts[k + 1][0]) / 2
      const my = (pts[k][1] + pts[k + 1][1]) / 2
      ctx.quadraticCurveTo(pts[k][0], pts[k][1], mx, my)
    }
    const last = pts[pts.length - 1]
    ctx.lineTo(last[0], last[1])
    ctx.stroke()
    ctx.globalAlpha = Math.min(1, alpha * 3)
    ctx.shadowBlur = 6
    ctx.beginPath()
    ctx.arc(last[0], last[1], Math.max(1.8, Math.min(s * 0.34, 3.4)), 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.shadowBlur = 0
  ctx.globalAlpha = 1
}

const restartCache = new WeakMap<XY[], XY[]>()
/**
 * A rollout keeps running after a goal or the ball going out, and the restart teleports the ball
 * (e.g. 25 m -> goal line -> centre spot). Draw each future only up to that teleport.
 */
function untilRestart(path: XY[]): XY[] {
  const hit = restartCache.get(path)
  if (hit) return hit
  let n = path.length
  for (let k = 1; k < path.length; k++) {
    const d = Math.hypot(path[k][0] - path[k - 1][0], path[k][1] - path[k - 1][1])
    // > 22 m in one sample: a restart (the first step may be the shot or pass itself)
    if (d > 22 && k > 1) {
      n = k
      break
    }
  }
  const out = path.slice(0, n)
  restartCache.set(path, out)
  return out
}

/** Pulsing ring where the decision was taken (the frozen ball). */
function drawDecision(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, now: number) {
  const k = (now % 1600) / 1600
  ctx.strokeStyle = `rgba(255,200,61,${0.9 * (1 - k)})`
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.arc(x, y, r * (1 + k * 2.4), 0, Math.PI * 2)
  ctx.stroke()
  ctx.strokeStyle = '#ffc83d'
  ctx.beginPath()
  ctx.arc(x, y, r, 0, Math.PI * 2)
  ctx.stroke()
}

function drawTag(ctx: CanvasRenderingContext2D, label: string, x: number, y: number, r: number, color: string, alpha: number) {
  const fs = Math.max(11, Math.round(r * 1.25))
  ctx.font = `700 ${fs}px "Barlow Condensed", sans-serif`
  const tw = ctx.measureText(label).width
  const pw = tw + fs * 1.1
  const ph = fs * 1.45
  ctx.globalAlpha = alpha
  ctx.fillStyle = 'rgba(8,12,18,0.88)'
  ctx.beginPath()
  ctx.roundRect(x - pw / 2, y - ph, pw, ph, 3)
  ctx.fill()
  ctx.fillStyle = color
  ctx.fillRect(x - pw / 2, y - ph, 3, ph)
  ctx.beginPath()
  ctx.moveTo(x - 5, y)
  ctx.lineTo(x + 5, y)
  ctx.lineTo(x, y + 5)
  ctx.fillStyle = 'rgba(8,12,18,0.88)'
  ctx.fill()
  ctx.fillStyle = '#fff'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(label, x + 1.5, y - ph / 2 + 1)
  ctx.globalAlpha = 1
}
