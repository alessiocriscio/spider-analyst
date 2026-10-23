// The spider, drawn and animated like the one in the @buildwithbrock clips:
// a narrow black body with a blue outline and a cyan head dot, eight cyan legs of
// three rigid segments with pink joints and feet, a silk line trailing behind.
// Feet stay planted on words until they fall about a stride behind, then step,
// two alternating sets of four, never more than four in the air.
// Everything is in document pixels; U scales the spider to the text it reads.

export const COLORS = {
  body: "#0b0d12", outline: "#3b6cff", head: "#4fe3ff", leg: "#3fd4f5", joint: "#ff2d8f",
  silk: "#5cc2ff", ping: "#ff2d8f", sight: "#27c8ff",
};
const BODY_LEN = 45, BODY_WID = 15, SEG = 46;
const LEG_ANG = [-0.55, -1.15, -1.95, -2.55, 0.55, 1.15, 1.95, 2.55];   // from the heading, left side negative
const LEG_R = [112, 118, 116, 106, 112, 118, 116, 106];               // resting distance of each foot
const HIP_ALONG = [0.38, 0.13, -0.12, -0.36];
const STEP_MIN = 18, MAX_SWING = 4;

export class Spider {
  constructor(U = 1) {
    this.U = U;
    this.x = 0; this.y = 0;
    this.heading = Math.PI / 2;           // facing down the page
    this.vel = { x: 0, y: 0 };
    this.bv = { x: 0, y: 0 };
    this.feet = []; this.anim = {}; this.joints = []; this.lastStep = [];
    this.wordNear = null;                 // (x, y, r) -> {x, y, word} | null
    this.onLand = null;                   // (word) -> void
    this.speed = 1;
    this.silkAnchor = null;
    this.t = 0;
  }

  place(x, y, heading = Math.PI / 2) {
    this.x = x; this.y = y; this.heading = heading;
    this.vel = { x: 0, y: 0 }; this.bv = { x: 0, y: 0 };
    this.anim = {}; this.joints = []; this.lastStep = []; this.silkAnchor = null;
    this.feet = LEG_ANG.map((_, i) => this.snap(this.rest(i)));
  }

  rest(i) {
    const a = this.heading + LEG_ANG[i], r = LEG_R[i] * this.U;
    return { x: this.x + Math.cos(a) * r, y: this.y + Math.sin(a) * r };
  }

  snap(p) {
    // settle on a word only if one is right there; never reach for one
    const w = this.wordNear ? this.wordNear(p.x, p.y, 16 * this.U) : null;
    return w ? { x: w.x, y: w.y, word: w.word } : { x: p.x, y: p.y, word: null };
  }

  head(d = 16) {
    return { x: this.x + Math.cos(this.heading) * d * this.U, y: this.y + Math.sin(this.heading) * d * this.U };
  }

  // follow a moving goal with a damped spring: the body lags a little and the legs catch up
  update(goal, dt, face = null) {
    dt = Math.max(1e-4, Math.min(dt, 0.05));
    this.t += dt;
    const k = 60, c = 2 * Math.sqrt(k) * 0.95;
    this.bv.x += (k * (goal.x - this.x) - c * this.bv.x) * dt;
    this.bv.y += (k * (goal.y - this.y) - c * this.bv.y) * dt;
    const px = this.x, py = this.y;
    this.x += this.bv.x * dt; this.y += this.bv.y * dt;
    const vx = (this.x - px) / dt, vy = (this.y - py) / dt;
    this.vel = { x: this.vel.x * 0.85 + vx * 0.15, y: this.vel.y * 0.85 + vy * 0.15 };
    const vm = Math.hypot(this.vel.x, this.vel.y);
    const want = vm > 8 * this.U ? Math.atan2(this.vel.y, this.vel.x) : face;
    if (want !== null && want !== undefined) {
      const d = Math.atan2(Math.sin(want - this.heading), Math.cos(want - this.heading));
      this.heading += d * Math.min(1, dt * (vm > 8 * this.U ? 5 : 2.5));
    }
    this.advance(dt);
    this.step();
  }

  advance(dt) {
    for (const key of Object.keys(this.anim)) {
      const a = this.anim[key], i = +key;
      a.t = Math.min(1, a.t + dt / a.dur);
      const s = a.t * a.t * (3 - 2 * a.t);
      if (a.t >= 1) {
        this.feet[i] = { x: a.to.x, y: a.to.y, word: a.to.word };
        delete this.anim[key];
        if (a.to.word && this.onLand) this.onLand(a.to.word);
        continue;
      }
      // smooth start and finish with a small sideways arc
      const dx = a.to.x - a.from.x, dy = a.to.y - a.from.y, dl = Math.hypot(dx, dy) || 1;
      const arc = Math.min(6 * this.U, dl * 0.12) * Math.sin(Math.PI * a.t);
      this.feet[i] = { x: a.from.x + dx * s - dy / dl * arc, y: a.from.y + dy * s + dx / dl * arc, word: null };
    }
  }

  step() {
    const now = this.t, U = this.U;
    const moving = Object.keys(this.anim).length;
    if (moving >= MAX_SWING) return;
    const v = this.vel, vm = Math.hypot(v.x, v.y);
    const half = Math.max(STEP_MIN * U, Math.min(80 * U, vm * 0.24));
    const swing = 0.18 / this.speed;
    const reachMax = 3 * SEG * U * 0.88;
    const cand = [];
    for (let i = 0; i < 8; i++) {
      if (this.anim[i] || now - (this.lastStep[i] || -1) < 0.04) continue;
      const f = this.feet[i], rest = this.rest(i);
      const dist = f ? Math.hypot(f.x - rest.x, f.y - rest.y) : 1e9;
      const behind = f && vm > 1 ? ((rest.x - f.x) * v.x + (rest.y - f.y) * v.y) / vm : dist;
      const strain = Math.max(behind, dist - 1.5 * half);
      const hip = this.hip(i);
      const reach = f ? Math.hypot(f.x - hip.x, f.y - hip.y) : 1e9;
      if (strain > half || reach > reachMax) {
        const nb = [i - 1, i + 1].filter((j) => j >= 0 && j < 8 && (j >> 2) === (i >> 2));
        const urgency = strain + (reach > reachMax ? 999 : 0) - (nb.some((j) => this.anim[j]) ? 60 * U : 0) + (i % 3) * 0.1;
        // land half a stride ahead, plus the distance travelled during the swing
        const to = vm > 1 ? { x: rest.x + v.x / vm * half + v.x * swing, y: rest.y + v.y / vm * half + v.y * swing } : rest;
        cand.push([urgency, i, to]);
      }
    }
    cand.sort((a, b) => b[0] - a[0]);
    for (const [, i, to] of cand.slice(0, MAX_SWING - moving)) {
      const from = this.feet[i] || { x: this.x, y: this.y };
      this.anim[i] = { from: { x: from.x, y: from.y }, to: this.snap(to), t: 0, dur: 0.18 / this.speed };
      this.lastStep[i] = now;
    }
  }

  hip(i) {
    const h = this.heading, side = i < 4 ? -1 : 1, U = this.U;
    const ux = Math.cos(h), uy = Math.sin(h);
    const sx = Math.cos(h + side * Math.PI / 2), sy = Math.sin(h + side * Math.PI / 2);
    const along = HIP_ALONG[i % 4] * BODY_LEN * U;
    return { x: this.x + ux * along + sx * 0.5 * BODY_WID * U, y: this.y + uy * along + sy * 0.5 * BODY_WID * U, sx, sy };
  }

  // three rigid segments, solved by FABRIK from the previous pose with a steady outward bend
  leg(i) {
    const hip = this.hip(i), foot = this.feet[i], L = SEG * this.U;
    let j = this.joints[i];
    if (!j) {
      j = [{ x: hip.x, y: hip.y }, { x: hip.x + hip.sx * L, y: hip.y + hip.sy * L },
        { x: (hip.x + hip.sx * L + foot.x) / 2 + hip.sx * L * 0.3, y: (hip.y + hip.sy * L + foot.y) / 2 + hip.sy * L * 0.3 },
        { x: foot.x, y: foot.y }];
    }
    j[1].x += hip.sx * 0.5 * this.U; j[1].y += hip.sy * 0.5 * this.U;
    j[2].x += hip.sx * 0.15 * this.U; j[2].y += hip.sy * 0.15 * this.U;
    for (let it = 0; it < 10; it++) {
      j[3] = { x: foot.x, y: foot.y };
      for (let k = 2; k >= 0; k--) {
        const dx = j[k].x - j[k + 1].x, dy = j[k].y - j[k + 1].y, d = Math.hypot(dx, dy) || 1;
        j[k] = { x: j[k + 1].x + dx / d * L, y: j[k + 1].y + dy / d * L };
      }
      j[0] = { x: hip.x, y: hip.y };
      for (let k = 1; k <= 3; k++) {
        const dx = j[k].x - j[k - 1].x, dy = j[k].y - j[k - 1].y, d = Math.hypot(dx, dy) || 1;
        j[k] = { x: j[k - 1].x + dx / d * L, y: j[k - 1].y + dy / d * L };
      }
      if (Math.hypot(j[3].x - foot.x, j[3].y - foot.y) < 0.3) break;
    }
    this.joints[i] = j;
    return [j[0], j[1], j[2], { x: foot.x, y: foot.y }];
  }

  // ctx is in document coordinates
  draw(ctx) {
    const U = this.U, h = this.heading;
    // silk from the back end to an anchor behind and above, re-anchored when it gets long
    const tail = { x: this.x - Math.cos(h) * 9 * U, y: this.y - Math.sin(h) * 9 * U };
    const a = this.silkAnchor;
    if (!a || Math.hypot(a.x - tail.x, a.y - tail.y) > 420 * U) {
      const ang = h + Math.PI + (Math.random() - 0.5) * 0.12;   // silk hangs almost straight up
      this.silkAnchor = { x: tail.x + Math.cos(ang) * 260 * U, y: tail.y + Math.min(-120 * U, Math.sin(ang) * 260 * U) };
    }
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    ctx.strokeStyle = COLORS.silk; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(tail.x, tail.y); ctx.lineTo(this.silkAnchor.x, this.silkAnchor.y); ctx.stroke();

    // legs
    const r = Math.max(1.8, 2.5 * U);
    ctx.strokeStyle = COLORS.leg; ctx.lineWidth = 2;
    const legs = this.feet.map((_, i) => this.leg(i));
    for (const p of legs) {
      ctx.beginPath(); ctx.moveTo(p[0].x, p[0].y);
      for (let k = 1; k < 4; k++) ctx.lineTo(p[k].x, p[k].y);
      ctx.stroke();
    }
    ctx.fillStyle = COLORS.joint;
    for (const p of legs) for (let k = 1; k < 4; k++) { ctx.beginPath(); ctx.arc(p[k].x, p[k].y, r, 0, Math.PI * 2); ctx.fill(); }

    // body: narrow outlined rectangle along the heading, head dot at the front
    ctx.save();
    ctx.translate(this.x, this.y);
    ctx.rotate(h - Math.PI / 2);
    ctx.fillStyle = COLORS.body; ctx.strokeStyle = COLORS.outline; ctx.lineWidth = 2;
    roundRect(ctx, -BODY_WID * U / 2, -BODY_LEN * U / 2, BODY_WID * U, BODY_LEN * U, 2 * U);
    ctx.fill(); ctx.stroke();
    ctx.restore();
    const hd = this.head(16);
    ctx.fillStyle = COLORS.head;
    ctx.beginPath(); ctx.arc(hd.x, hd.y, Math.max(2.5, 3.6 * U), 0, Math.PI * 2); ctx.fill();
  }
}

export function roundRect(ctx, x, y, w, h, r) {
  r = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

// a quick line that shoots from the head to a word, holds, then fades (pink ping / cyan sight)
export function pingLine(ctx, from, to, t, color, width = 1.6) {
  const grow = Math.min(1, t / 0.25), fade = t < 0.55 ? 1 : Math.max(0, 1 - (t - 0.55) / 0.45);
  ctx.save();
  ctx.globalAlpha = fade;
  ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineCap = "round";
  ctx.beginPath(); ctx.moveTo(from.x, from.y);
  ctx.lineTo(from.x + (to.x - from.x) * grow, from.y + (to.y - from.y) * grow);
  ctx.stroke();
  ctx.restore();
}
