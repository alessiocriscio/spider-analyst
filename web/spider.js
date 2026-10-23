// The spider: body, eight two-segment legs solved with inverse kinematics,
// an alternating gait, and feet that land on real words of the document.
// All coordinates are document pixels; `size` is the body length in document pixels.

const TAU = Math.PI * 2;
const SILK = "#ff2e88";

// rest direction of each leg from the heading (radians), front to back
const REST = [0.62, 1.2, 1.78, 2.4];
// legs that must not lift together: neighbours on the same side and the mirror leg
function neighbours(i) {
  const side = i < 4 ? 0 : 4, k = i % 4, out = [(i + 4) % 8];
  if (k > 0) out.push(side + k - 1);
  if (k < 3) out.push(side + k + 1);
  return out;
}

export class Spider {
  constructor(size = 30) {
    this.size = size;
    this.x = 0; this.y = 0; this.angle = -Math.PI / 2;
    this.vx = 0; this.vy = 0;
    this.t = 0;
    this.snap = null;            // (x, y) -> {x, y, rect} | null : put a foot on a word
    this.onStep = null;          // (rect) -> void : a foot touched a word
    this.legs = [];
    for (let i = 0; i < 8; i++) {
      const side = i < 4 ? -1 : 1, k = i % 4;
      this.legs.push({ side, k, fx: 0, fy: 0, from: null, to: null, p: 1, nb: neighbours(i) });
    }
  }

  get reach() { return this.size * 1.75; }
  get segA() { return this.size * 1.2; }
  get segB() { return this.size * 1.45; }

  place(x, y, angle = this.angle) {
    this.x = x; this.y = y; this.angle = angle;
    for (const L of this.legs) {
      const r = this.restPoint(L);
      L.fx = r.x; L.fy = r.y; L.p = 1; L.from = L.to = null;
    }
  }

  hip(L) {
    const a = this.angle, along = (0.12 - L.k * 0.09) * this.size;
    const across = L.side * 0.16 * this.size;
    return { x: this.x + Math.cos(a) * along - Math.sin(a) * across, y: this.y + Math.sin(a) * along + Math.cos(a) * across };
  }

  restPoint(L, lead = 0) {
    const a = this.angle + L.side * REST[L.k];
    const r = this.reach * (L.k === 0 || L.k === 3 ? 1.05 : 0.95);
    return { x: this.x + Math.cos(a) * r + this.vx * lead, y: this.y + Math.sin(a) * r + this.vy * lead };
  }

  // move the body to (x, y); legs follow on their own
  update(x, y, dt, faceAngle = null) {
    dt = Math.max(1e-4, Math.min(dt, 0.05));
    this.t += dt;
    const vx = (x - this.x) / dt, vy = (y - this.y) / dt;
    this.vx += (vx - this.vx) * Math.min(1, dt * 12);
    this.vy += (vy - this.vy) * Math.min(1, dt * 12);
    this.x = x; this.y = y;
    const speed = Math.hypot(this.vx, this.vy);
    const want = speed > this.size * 0.6 ? Math.atan2(this.vy, this.vx) : faceAngle;
    if (want !== null) {
      let d = ((want - this.angle + Math.PI) % TAU + TAU) % TAU - Math.PI;
      this.angle += d * Math.min(1, dt * (speed > this.size * 0.6 ? 7 : 3));
    }
    const stepTime = Math.max(0.07, Math.min(0.16, this.size * 2.4 / Math.max(speed, 1)));
    const lead = Math.min(0.22, stepTime * 1.4);
    // advance stepping legs
    for (const L of this.legs) {
      if (L.p < 1) {
        L.p = Math.min(1, L.p + dt / L.dur);
        const e = L.p < 0.5 ? 2 * L.p * L.p : 1 - (-2 * L.p + 2) ** 2 / 2;
        L.fx = L.from.x + (L.to.x - L.from.x) * e;
        L.fy = L.from.y + (L.to.y - L.from.y) * e;
        if (L.p === 1 && L.to.rect && this.onStep) this.onStep(L.to.rect);
      }
    }
    // start new steps: the leg furthest from where it wants to be goes first
    const cands = this.legs.map((L, i) => {
      const r = this.restPoint(L, lead);
      return { i, r, d: Math.hypot(L.fx - r.x, L.fy - r.y) };
    }).sort((a, b) => b.d - a.d);
    for (const c of cands) {
      const L = this.legs[c.i];
      if (L.p < 1 || c.d < this.reach * 0.38) continue;
      if (L.nb.some((j) => this.legs[j].p < 1)) continue;
      let to = { x: c.r.x, y: c.r.y, rect: null };
      if (this.snap) {
        const s = this.snap(c.r.x, c.r.y, this.size * 0.45);
        if (s) to = s;
      }
      L.from = { x: L.fx, y: L.fy }; L.to = to; L.p = 0; L.dur = stepTime;
    }
    // idle twitch so a resting spider still looks alive
    if (speed < 2 && Math.random() < dt * 0.6) {
      const L = this.legs[(Math.random() * 8) | 0];
      if (L.p === 1 && !L.nb.some((j) => this.legs[j].p < 1)) {
        const r = this.restPoint(L);
        L.from = { x: L.fx, y: L.fy };
        L.to = { x: r.x + (Math.random() - 0.5) * this.size * 0.3, y: r.y + (Math.random() - 0.5) * this.size * 0.3, rect: null };
        L.p = 0; L.dur = 0.16;
      }
    }
  }

  // two-bone IK, knee bent away from the body
  knee(h, f) {
    const a = this.segA, b = this.segB;
    let dx = f.x - h.x, dy = f.y - h.y;
    let d = Math.hypot(dx, dy);
    const dmax = (a + b) * 0.999, dmin = Math.abs(a - b) + 1e-3;
    if (d > dmax) { f = { x: h.x + dx / d * dmax, y: h.y + dy / d * dmax }; d = dmax; dx = f.x - h.x; dy = f.y - h.y; }
    d = Math.max(d, dmin);
    const base = Math.atan2(dy, dx);
    const A = Math.acos(Math.max(-1, Math.min(1, (a * a + d * d - b * b) / (2 * a * d))));
    const k1 = { x: h.x + Math.cos(base + A) * a, y: h.y + Math.sin(base + A) * a };
    const k2 = { x: h.x + Math.cos(base - A) * a, y: h.y + Math.sin(base - A) * a };
    const d1 = Math.hypot(k1.x - this.x, k1.y - this.y), d2 = Math.hypot(k2.x - this.x, k2.y - this.y);
    return { k: d1 > d2 ? k1 : k2, f };
  }

  // ctx already transformed to document coordinates; px = size of one screen pixel in document units
  draw(ctx, px) {
    const s = this.size, a = this.angle;
    const bob = Math.sin(this.t * 9) * 0.03 * s * Math.min(1, Math.hypot(this.vx, this.vy) / (s * 4));
    const ca = Math.cos(a), sa = Math.sin(a);
    const P = (u, v) => ({ x: this.x + ca * u - sa * v, y: this.y + sa * u + ca * v + bob });

    // shadow
    ctx.save();
    ctx.globalAlpha = 0.18;
    ctx.fillStyle = "#000";
    ctx.beginPath();
    ctx.ellipse(this.x + 3 * px, this.y + 6 * px, s * 0.95, s * 0.7, a, 0, TAU);
    ctx.fill();
    ctx.restore();

    // legs: pink edge under a black core
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    const legW = Math.max(s * 0.075, 1.8 * px);
    const segs = this.legs.map((L) => {
      const h = this.hip(L);
      const lift = L.p < 1 ? Math.sin(Math.PI * L.p) * s * 0.35 : 0;
      const { k, f } = this.knee(h, { x: L.fx, y: L.fy - lift });
      return { h, k: { x: k.x, y: k.y - lift * 0.5 }, f, lift };
    });
    for (const pass of [0, 1]) {
      ctx.strokeStyle = pass ? "#000" : SILK;
      for (const g of segs) {
        ctx.lineWidth = pass ? legW : legW + 2.2 * px;
        ctx.beginPath();
        ctx.moveTo(g.h.x, g.h.y); ctx.lineTo(g.k.x, g.k.y); ctx.lineTo(g.f.x, g.f.y);
        ctx.stroke();
      }
    }
    // feet
    ctx.fillStyle = SILK;
    for (const g of segs) {
      ctx.beginPath(); ctx.arc(g.f.x, g.f.y, Math.max(legW * 0.55, 1.2 * px), 0, TAU); ctx.fill();
    }

    // body
    ctx.lineWidth = 1.8 * px;
    ctx.strokeStyle = SILK;
    ctx.fillStyle = "#000";
    const abd = P(-0.62 * s, 0), tho = P(0.08 * s, 0), head = P(0.42 * s, 0);
    ctx.beginPath(); ctx.ellipse(abd.x, abd.y, s * 0.62, s * 0.48, a, 0, TAU); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.ellipse(tho.x, tho.y, s * 0.34, s * 0.29, a, 0, TAU); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.ellipse(head.x, head.y, s * 0.17, s * 0.16, a, 0, TAU); ctx.fill(); ctx.stroke();
    // abdomen mark: a small pink chevron
    ctx.lineWidth = Math.max(1.4 * px, s * 0.06);
    ctx.beginPath();
    const m1 = P(-0.42 * s, -0.17 * s), m2 = P(-0.7 * s, 0), m3 = P(-0.42 * s, 0.17 * s);
    ctx.moveTo(m1.x, m1.y); ctx.lineTo(m2.x, m2.y); ctx.lineTo(m3.x, m3.y);
    ctx.stroke();
    // eyes
    ctx.fillStyle = SILK;
    for (const v of [-0.07, 0.07]) {
      const e = P(0.5 * s, v * s);
      ctx.beginPath(); ctx.arc(e.x, e.y, Math.max(s * 0.035, 0.9 * px), 0, TAU); ctx.fill();
    }
  }

  // where silk leaves the body
  spinneret() {
    const a = this.angle;
    return { x: this.x - Math.cos(a) * this.size * 1.2, y: this.y - Math.sin(a) * this.size * 1.2 };
  }
  mouth() {
    const a = this.angle;
    return { x: this.x + Math.cos(a) * this.size * 0.55, y: this.y + Math.sin(a) * this.size * 0.55 };
  }
}

// a silk thread with a little sag
export function thread(ctx, from, to, px, alpha = 1) {
  const mx = (from.x + to.x) / 2, my = (from.y + to.y) / 2;
  const len = Math.hypot(to.x - from.x, to.y - from.y);
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = SILK;
  ctx.lineWidth = 1.5 * px;
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.quadraticCurveTo(mx, my + Math.min(len * 0.12, 40 * px), to.x, to.y);
  ctx.stroke();
  ctx.fillStyle = SILK;
  ctx.beginPath(); ctx.arc(to.x, to.y, 2.4 * px, 0, TAU); ctx.fill();
  ctx.restore();
}
