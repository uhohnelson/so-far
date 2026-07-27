/** Lightweight canvas burst — no dependency. */
export function fireConfetti() {
  if (typeof document === 'undefined') return
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

  const canvas = document.createElement('canvas')
  canvas.setAttribute('aria-hidden', 'true')
  Object.assign(canvas.style, {
    position: 'fixed',
    inset: '0',
    width: '100%',
    height: '100%',
    pointerEvents: 'none',
    zIndex: '9999',
  })
  document.body.appendChild(canvas)

  const ctx = canvas.getContext('2d')
  if (!ctx) {
    canvas.remove()
    return
  }

  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const resize = () => {
    canvas.width = Math.floor(window.innerWidth * dpr)
    canvas.height = Math.floor(window.innerHeight * dpr)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }
  resize()

  const colors = ['#ffd400', '#7c3aed', '#22c55e', '#ff6b6b', '#3b82f6', '#111']
  const cx = window.innerWidth / 2
  const cy = window.innerHeight * 0.38
  const count = 72
  const pieces = Array.from({ length: count }, (_, i) => {
    const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.4
    const speed = 4 + Math.random() * 7
    return {
      x: cx,
      y: cy,
      vx: Math.cos(angle) * speed * (0.55 + Math.random() * 0.7),
      vy: Math.sin(angle) * speed * 0.35 - (5 + Math.random() * 6),
      w: 5 + Math.random() * 5,
      h: 7 + Math.random() * 6,
      rot: Math.random() * Math.PI,
      vr: (Math.random() - 0.5) * 0.35,
      color: colors[i % colors.length],
      life: 1,
    }
  })

  const gravity = 0.18
  const drag = 0.992
  let frame = 0
  const maxFrames = 90

  const tick = () => {
    frame += 1
    ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
    let alive = false
    for (const p of pieces) {
      p.vy += gravity
      p.vx *= drag
      p.vy *= drag
      p.x += p.vx
      p.y += p.vy
      p.rot += p.vr
      p.life = Math.max(0, 1 - frame / maxFrames)
      if (p.life <= 0) continue
      alive = true
      ctx.save()
      ctx.translate(p.x, p.y)
      ctx.rotate(p.rot)
      ctx.globalAlpha = p.life
      ctx.fillStyle = p.color
      ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h)
      ctx.restore()
    }
    if (alive && frame < maxFrames) {
      requestAnimationFrame(tick)
    } else {
      canvas.remove()
    }
  }
  requestAnimationFrame(tick)
}
