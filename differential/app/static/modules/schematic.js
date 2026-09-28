// Schematic panel: the circuit's SVG (light or dark variant) with clickable
// test-point hotspots placed from the test-point map (SVG viewBox units),
// hazard rings, reading labels, a pulsing "next" marker, a measurement popover,
// and pan/zoom (buttons, wheel, drag, keyboard).
//
// Zoom changes the stage's layout size (not a CSS scale), so the SVG is
// re-rasterised crisply at every zoom level; hotspots are positioned in percent
// of the stage and keep a minimum on-screen size.

import { h, icon, clear, replaceChildren, prefersReducedMotion, nextId } from "./dom.js";
import {
  HAZARD_TEXT, KIND_SHORT, hazardLevel, kindOf, stageName, targetOf,
} from "./format.js";
import { readingForm } from "./forms.js";

const MARKER_UNITS = 11; // diameter of the drawn test-point ring in SVG units

/** Compact label text for a reading on the drawing: DC as a plain voltage, gains in dB. */
function shortReading(r) {
  const kind = kindOf(r.key);
  let text = String(r.text || "");
  if (kind === "ac" || kind === "ac20" || kind === "ac20k") {
    const m = text.match(/\(([-+]?[0-9.]+ dB)\)/);
    if (m) text = m[1];
  }
  text = text.replace(/ rms$/, "");
  return [kind === "dc" ? "" : KIND_SHORT[kind] || kind, text];
}
const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));

function rectOverlap(a, b) {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const hgt = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  return w > 0 && hgt > 0 ? w * hgt : 0;
}

export class SchematicView {
  /**
   * handlers: {
   *   measure(key, button) -> Promise<string>   ("" on success, else an error message)
   *   enterReading(key, value, button) -> Promise<string>
   *   canAct() -> boolean                          (a session is active and idle)
   * }
   */
  constructor(root, handlers) {
    this.root = root;
    this.handlers = handlers;
    this.circuit = null;
    this.theme = "light";
    this.W = 1;
    this.H = 1;
    this.s = 1;
    this.tx = 0;
    this.ty = 0;
    this.userMoved = false;
    this.tps = []; // [{id, x, y, info, el}]
    this.readings = [];
    this.pending = null;
    this.sessionActive = false;
    this.labels = []; // [{tp, el, w, h, isNext}]
    this.openTp = null;
    this.openForm = null; // key of the measurement whose entry form is open
    this.lastPendingTp = null;
    this.build();
  }

  // ------------------------------------------------------------------ DOM
  build() {
    const r = this.root;
    clear(r);
    this.nameEl = h("span", { class: "sch-name" }, "");
    this.hintEl = h("span", { class: "sch-hint" }, "Click a test point to see its measurements");
    const tool = (name, label, onClick, key) => h("button", {
      type: "button", class: "btn btn-icon btn-sm", "aria-label": label,
      title: key ? `${label} (${key})` : label, onclick: onClick,
    }, icon(name));
    this.focusBtn = tool("target", "Centre the recommended test point", () => this.focusPending(true));
    this.focusBtn.disabled = true;
    const tools = h("div", { class: "sch-tools", role: "toolbar", "aria-label": "Schematic view" },
      tool("minus", "Zoom out", () => this.zoomCenter(1 / 1.35), "−"),
      tool("plus", "Zoom in", () => this.zoomCenter(1.35), "+"),
      tool("fit", "Fit the whole schematic", () => this.fit(true), "0"),
      this.focusBtn);
    const head = h("div", { class: "panel-head sch-head" },
      h("div", { class: "sch-titles" },
        h("h2", { class: "panel-title", id: "sch-title" }, "Schematic"),
        this.nameEl),
      this.hintEl,
      tools);

    this.img = h("img", { class: "sch-img", alt: "", draggable: "false", decoding: "async" });
    this.layer = h("div", { class: "sch-layer" });
    this.stage = h("div", { class: "sch-stage" }, this.img, this.layer);
    this.legend = h("div", { class: "sch-legend", "aria-label": "Legend" });
    this.popover = h("div", {
      class: "sch-popover", role: "dialog", "aria-modal": "false", hidden: true,
    });
    this.emptyEl = h("div", { class: "sch-empty" }, "Loading schematic…");
    const helpId = nextId("sch-help");
    this.viewport = h("div", {
      class: "sch-viewport", tabindex: "0", role: "group",
      "aria-label": "Schematic", "aria-describedby": helpId,
    }, this.stage, this.legend, this.popover, this.emptyEl,
    h("p", { class: "sr-only", id: helpId },
      "Drag or use the arrow keys to pan, plus and minus to zoom, 0 to fit. Test points are buttons; press Tab to reach them."));
    r.append(head, this.viewport);
    this.bindEvents();
  }

  bindEvents() {
    const vp = this.viewport;
    vp.addEventListener("wheel", (e) => {
      if (!this.circuit) return;
      if (e.target.closest(".sch-popover")) return; // let a long popover scroll
      e.preventDefault();
      const rect = vp.getBoundingClientRect();
      const unit = e.deltaMode === 1 ? 0.05 : e.deltaMode === 2 ? 1 : 0.0015;
      const factor = Math.exp(-e.deltaY * unit * (e.ctrlKey ? 4 : 1));
      this.zoomAt(e.clientX - rect.left, e.clientY - rect.top, factor, false);
    }, { passive: false });

    vp.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || !this.circuit) return;
      if (e.target.closest(".tp, .sch-popover, .sch-legend")) return;
      this.drag = { id: e.pointerId, x: e.clientX, y: e.clientY, tx: this.tx, ty: this.ty, moved: false };
      vp.setPointerCapture(e.pointerId);
    });
    vp.addEventListener("pointermove", (e) => {
      const d = this.drag;
      if (!d || d.id !== e.pointerId) return;
      const dx = e.clientX - d.x;
      const dy = e.clientY - d.y;
      if (!d.moved && Math.hypot(dx, dy) < 4) return;
      if (!d.moved) {
        d.moved = true;
        vp.classList.add("is-panning");
      }
      this.tx = d.tx + dx;
      this.ty = d.ty + dy;
      this.userMoved = true;
      this.clampPan();
      this.apply(false);
    });
    const end = (e) => {
      const d = this.drag;
      if (!d || d.id !== e.pointerId) return;
      this.drag = null;
      vp.classList.remove("is-panning");
      try { vp.releasePointerCapture(e.pointerId); } catch { /* already released */ }
      if (!d.moved && e.type === "pointerup") this.closePopover(false);
    };
    vp.addEventListener("pointerup", end);
    vp.addEventListener("pointercancel", end);
    vp.addEventListener("dblclick", (e) => {
      if (e.target.closest(".tp, .sch-popover, .sch-legend")) return;
      const rect = vp.getBoundingClientRect();
      this.zoomAt(e.clientX - rect.left, e.clientY - rect.top, 1.8, true);
    });
    vp.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.openTp) {
        e.preventDefault();
        this.closePopover(true);
        return;
      }
      if (e.target !== vp) return;
      const step = e.shiftKey ? 200 : 60;
      const moves = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
      if (moves[e.key]) {
        e.preventDefault();
        this.tx += moves[e.key][0];
        this.ty += moves[e.key][1];
        this.userMoved = true;
        this.clampPan();
        this.apply(true);
      } else if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        this.zoomCenter(1.35);
      } else if (e.key === "-" || e.key === "_") {
        e.preventDefault();
        this.zoomCenter(1 / 1.35);
      } else if (e.key === "0") {
        e.preventDefault();
        this.fit(true);
      }
    });
    document.addEventListener("pointerdown", (e) => {
      if (!this.openTp) return;
      if (e.target.closest(".sch-popover") || e.target.closest(".tp")) return;
      if (this.viewport.contains(e.target)) return; // handled by the viewport's own click logic
      this.closePopover(false);
    });
    if (window.ResizeObserver) {
      this.ro = new ResizeObserver(() => requestAnimationFrame(() => this.onResize()));
      this.ro.observe(vp);
    } else {
      window.addEventListener("resize", () => this.onResize());
    }
  }

  // -------------------------------------------------------------- circuit
  setCircuit(circuit) {
    if (this.circuit && circuit && this.circuit.id === circuit.id) return;
    this.circuit = circuit;
    this.closePopover(false);
    this.readings = [];
    this.pending = null;
    this.lastPendingTp = null;
    clear(this.layer);
    this.tps = [];
    this.labels = [];
    if (!circuit) {
      this.nameEl.textContent = "";
      this.emptyEl.hidden = false;
      this.emptyEl.textContent = "No circuit selected.";
      return;
    }
    const map = circuit.schematic && circuit.schematic.testpoints ? circuit.schematic.testpoints : {};
    const vb = map.viewBox || [0, 0, map.width || 1000, map.height || 600];
    this.W = vb[2] || map.width || 1000;
    this.H = vb[3] || map.height || 600;
    this.nameEl.textContent = circuit.name;
    this.img.alt = `Schematic of the ${circuit.name}`;
    this.emptyEl.hidden = false;
    this.emptyEl.textContent = "Loading schematic…";
    const coords = map.test_points || {};
    const byId = new Map((circuit.test_points || []).map((tp) => [tp.id, tp]));
    const ids = Object.keys(coords).filter((id) => byId.has(id))
      .sort((a, b) => (parseInt(a.replace(/\D/g, ""), 10) || 0) - (parseInt(b.replace(/\D/g, ""), 10) || 0));
    for (const id of ids) {
      const info = byId.get(id);
      const c = coords[id];
      const level = hazardLevel(info);
      const btn = h("button", {
        type: "button",
        class: `tp hz-${level}`,
        dataset: { tp: id },
        "aria-haspopup": "dialog",
        "aria-expanded": "false",
        style: { left: `${(c.x - vb[0]) / this.W * 100}%`, top: `${(c.y - vb[1]) / this.H * 100}%` },
      },
      h("span", { class: "tp-pulse", "aria-hidden": "true" }),
      h("span", { class: "tp-ring", "aria-hidden": "true" }),
      level !== "lv" ? h("span", { class: "tp-badge", "aria-hidden": "true" }, icon("bolt")) : null,
      h("span", { class: "tp-tip", "aria-hidden": "true" },
        h("b", {}, id), ` ${info.name}`,
        level !== "lv" ? h("span", { class: "tp-tip-hz" }, ` · ${level === "hv" ? "HV" : "HV under fault"}`) : null));
      btn.addEventListener("click", () => this.togglePopover(id));
      this.layer.append(btn);
      this.tps.push({ id, x: c.x - vb[0], y: c.y - vb[1], info, el: btn });
    }
    this.renderLegend();
    this.updateAria();
    this.loadImage();
    this.userMoved = false;
    requestAnimationFrame(() => this.fit(false));
  }

  setTheme(theme) {
    this.theme = theme;
    if (this.circuit) this.loadImage();
  }

  loadImage() {
    const sch = this.circuit && this.circuit.schematic;
    if (!sch) return;
    const src = this.theme === "dark" ? sch.dark : sch.light;
    const other = this.theme === "dark" ? sch.light : sch.dark;
    if (this.img.getAttribute("src") !== src) {
      this.img.onload = () => { this.emptyEl.hidden = true; };
      this.img.onerror = () => {
        this.emptyEl.hidden = false;
        this.emptyEl.textContent = "The schematic image could not be loaded.";
      };
      this.img.src = src;
    } else {
      this.emptyEl.hidden = true;
    }
    if (other) {
      const pre = new Image();
      pre.src = other; // warm the cache so the theme toggle is instant
    }
  }

  renderLegend() {
    const present = new Set(this.tps.map((t) => hazardLevel(t.info)));
    const item = (cls, text, badge) => h("span", { class: "lg-item" },
      h("span", { class: `lg-ring ${cls}`, "aria-hidden": "true" }, badge ? icon("bolt") : null),
      h("span", {}, text));
    replaceChildren(this.legend,
      present.has("hv") ? item("hz-hv", "High voltage", true) : null,
      present.has("hv_under_fault") ? item("hz-hv_under_fault", "HV possible under a fault", true) : null,
      present.has("unknown") ? item("hz-unknown", "Hazard unknown", true) : null,
      present.has("lv") ? item("hz-lv", "Low voltage", false) : null,
      this.hasNext ? item("is-next-demo", "Recommended next", false) : null);
  }

  // ---------------------------------------------------------------- state
  /** update({readings, pending, sessionActive}) after every server state. */
  update({ readings = [], pending = null, sessionActive = false } = {}) {
    this.readings = readings;
    this.pending = pending;
    this.sessionActive = sessionActive;
    this.hintEl.textContent = sessionActive
      ? "Click a test point to measure it"
      : "Click a test point to see its measurements";
    const nextTp = pending && !pending.blocked ? pending.test_point : null;
    if (Boolean(nextTp) !== Boolean(this.hasNext)) {
      this.hasNext = Boolean(nextTp);
      this.renderLegend();
    }
    for (const t of this.tps) {
      t.el.classList.toggle("is-next", t.id === nextTp);
      t.el.classList.toggle("has-reading", readings.some((r) => targetOf(r.key) === t.id));
    }
    this.focusBtn.disabled = !nextTp;
    this.updateAria();
    this.renderLabels(nextTp);
    if (this.openTp) this.renderPopover(this.openTp, false);
    if (nextTp && nextTp !== this.lastPendingTp) {
      this.lastPendingTp = nextTp;
      if (!this.isVisible(nextTp, 56)) this.focusPending(true);
    } else if (!nextTp) {
      this.lastPendingTp = null;
    }
  }

  updateAria() {
    const nextTp = this.pending && !this.pending.blocked ? this.pending.test_point : null;
    for (const t of this.tps) {
      const level = hazardLevel(t.info);
      const n = (t.info.measurements || []).length;
      const taken = this.readings.filter((r) => targetOf(r.key) === t.id).length;
      const parts = [`${t.id}, ${t.info.name}`, HAZARD_TEXT[level]];
      if (t.id === nextTp) parts.push("recommended next");
      parts.push(`${n} measurement${n === 1 ? "" : "s"}${taken ? `, ${taken} recorded` : ""}`);
      t.el.setAttribute("aria-label", parts.join(". "));
    }
  }

  renderLabels(nextTp) {
    for (const l of this.labels) l.el.remove();
    this.labels = [];
    const byTp = new Map();
    for (const r of this.readings) {
      const tp = targetOf(r.key);
      if (!tp.startsWith("TP")) continue;
      if (!byTp.has(tp)) byTp.set(tp, []);
      byTp.get(tp).push(r);
    }
    const pos = new Map(this.tps.map((t) => [t.id, t]));
    if (nextTp && pos.has(nextTp)) {
      const kind = kindOf(this.pending.key);
      const el = h("div", { class: "tp-label tp-next-tag", "aria-hidden": "true" },
        h("span", { class: "tp-next-word" }, "Next"), ` ${KIND_SHORT[kind] || kind} at ${nextTp}`);
      this.layer.append(el);
      this.labels.push({ tp: pos.get(nextTp), el, isNext: true });
    }
    // Latest readings are placed first so they get the clearest spot.
    const order = [...byTp.entries()].sort((a, b) =>
      Math.max(...b[1].map((r) => r.step)) - Math.max(...a[1].map((r) => r.step)));
    const latestStep = Math.max(0, ...this.readings.map((r) => r.step));
    for (const [tp, rs] of order) {
      if (!pos.has(tp)) continue;
      rs.sort((a, b) => a.step - b.step);
      const el = h("div", {
        class: `tp-label tp-reading${rs.some((r) => r.step === latestStep) ? " is-latest" : ""}`,
        "aria-hidden": "true",
      },
      h("span", { class: "tp-label-id" }, tp),
      h("span", { class: "tp-label-vals" }, rs.map((r) => {
        const [kindText, value] = shortReading(r);
        return h("span", { class: "tp-label-val" },
          kindText ? h("span", { class: "tp-label-kind" }, `${kindText} `) : null, value);
      })),
      rs.length > 1 ? h("span", { class: "tp-label-more" }, `+${rs.length - 1}`) : null);
      this.layer.append(el);
      this.labels.push({ tp: pos.get(tp), el, isNext: false });
    }
    this.stage.classList.toggle("is-compact", this.s < 0.62);
    for (const l of this.labels) {
      l.el.style.left = `${l.tp.x / this.W * 100}%`;
      l.el.style.top = `${l.tp.y / this.H * 100}%`;
      l.w = l.el.offsetWidth;
      l.h = l.el.offsetHeight;
    }
    this.layoutLabels();
  }

  /** Greedy label placement: try 8 positions around each point, avoid overlaps. */
  layoutLabels() {
    if (!this.labels.length) return;
    // Zoomed out, a point with several readings shows only its latest one ("+n").
    const compact = this.s < 0.62;
    if (compact !== this.stage.classList.contains("is-compact")) {
      this.stage.classList.toggle("is-compact", compact);
      for (const l of this.labels) {
        l.w = l.el.offsetWidth;
        l.h = l.el.offsetHeight;
      }
    }
    const s = this.s;
    const d = this.ringDiameter();
    const r = d / 2 + 3;
    const placed = this.tps.map((t) => ({ x: t.x * s - d / 2, y: t.y * s - d / 2, w: d, h: d }));
    const stageW = this.W * s;
    const stageH = this.H * s;
    for (const l of this.labels) {
      if (!l.w) {
        l.w = l.el.offsetWidth;
        l.h = l.el.offsetHeight;
      }
      const cx = l.tp.x * s;
      const cy = l.tp.y * s;
      const { w, h: hh } = l;
      const k = r * 0.72;
      const cand = {
        n: [-w / 2, -r - hh - 2], s: [-w / 2, r + 2], e: [r + 2, -hh / 2], w: [-r - w - 2, -hh / 2],
        ne: [k, -k - hh], se: [k, k], nw: [-k - w, -k - hh], sw: [-k - w, k],
      };
      const prefs = l.isNext ? ["n", "s", "ne", "nw", "e", "w", "se", "sw"]
        : ["ne", "e", "se", "nw", "w", "sw", "s", "n"];
      let best = null;
      for (const p of prefs) {
        const [dx, dy] = cand[p];
        const box = { x: cx + dx, y: cy + dy, w, h: hh };
        let cost = 0;
        for (const o of placed) cost += rectOverlap(box, o);
        if (box.x < 0 || box.y < 0 || box.x + w > stageW || box.y + hh > stageH) cost += w * hh * 0.25;
        if (!best || cost < best.cost) best = { cost, dx, dy, box };
        if (cost === 0) break;
      }
      l.el.style.transform = `translate(${Math.round(best.dx)}px, ${Math.round(best.dy)}px)`;
      placed.push(best.box);
    }
  }

  // ------------------------------------------------------------- pan/zoom
  ringDiameter() {
    return clamp(MARKER_UNITS * this.s + 6, 13, 32);
  }

  viewportSize() {
    const r = this.viewport.getBoundingClientRect();
    return { w: r.width, h: r.height };
  }

  fitScale() {
    const { w, h: hh } = this.viewportSize();
    const pad = w < 500 ? 12 : 28;
    return Math.max(0.02, Math.min((w - 2 * pad) / this.W, (hh - 2 * pad - 36) / this.H));
  }

  fit(animate) {
    if (!this.circuit) return;
    const { w, h: hh } = this.viewportSize();
    if (w < 10 || hh < 10) return;
    this.lastSize = { w, h: hh };
    this.s = this.fitScale();
    this.tx = (w - this.W * this.s) / 2;
    this.ty = (hh - 36 - this.H * this.s) / 2; // leave room for the legend strip
    this.userMoved = false;
    this.apply(animate);
  }

  zoomCenter(factor) {
    const { w, h: hh } = this.viewportSize();
    this.zoomAt(w / 2, hh / 2, factor, true);
  }

  zoomAt(cx, cy, factor, animate) {
    if (!this.circuit) return;
    const fit = this.fitScale();
    const s1 = clamp(this.s * factor, fit * 0.7, Math.max(3, fit * 12));
    const k = s1 / this.s;
    if (Math.abs(k - 1) < 1e-4) return;
    this.tx = cx - (cx - this.tx) * k;
    this.ty = cy - (cy - this.ty) * k;
    this.s = s1;
    this.userMoved = true;
    this.clampPan();
    this.apply(animate);
  }

  clampPan() {
    const { w, h: hh } = this.viewportSize();
    const sw = this.W * this.s;
    const sh = this.H * this.s;
    const m = Math.min(120, w * 0.25, hh * 0.25);
    this.tx = clamp(this.tx, m - sw, w - m);
    this.ty = clamp(this.ty, m - sh, hh - m);
  }

  isVisible(tpId, margin = 0) {
    const t = this.tps.find((x) => x.id === tpId);
    if (!t) return true;
    const { w, h: hh } = this.viewportSize();
    const x = this.tx + t.x * this.s;
    const y = this.ty + t.y * this.s;
    return x >= margin && y >= margin && x <= w - margin && y <= hh - margin - 36;
  }

  centerOn(tpId, animate, zoomTo = null) {
    const t = this.tps.find((x) => x.id === tpId);
    if (!t) return;
    const { w, h: hh } = this.viewportSize();
    if (zoomTo) this.s = zoomTo;
    this.tx = w / 2 - t.x * this.s;
    this.ty = (hh - 36) / 2 - t.y * this.s;
    this.userMoved = true;
    this.clampPan();
    this.apply(animate);
  }

  /** Bring the recommended test point into view (zooming in a little if the view is at fit). */
  focusPending(animate) {
    const tp = this.pending && !this.pending.blocked ? this.pending.test_point : null;
    if (!tp) return;
    const fit = this.fitScale();
    const zoom = this.s < fit * 1.05 && this.isVisible(tp, 56) ? Math.min(fit * 2.2, Math.max(fit, 1.1)) : null;
    this.centerOn(tp, animate, zoom);
  }

  apply(animate) {
    const st = this.stage.style;
    const anim = Boolean(animate) && !prefersReducedMotion();
    this.stage.classList.toggle("is-animating", anim);
    st.width = `${this.W * this.s}px`;
    st.height = `${this.H * this.s}px`;
    st.transform = `translate(${Math.round(this.tx)}px, ${Math.round(this.ty)}px)`;
    const d = this.ringDiameter();
    this.stage.style.setProperty("--tp-d", `${d}px`);
    this.stage.style.setProperty("--tp-hit", `${Math.max(26, d + 10)}px`);
    this.layoutLabels();
    clearTimeout(this.animTimer);
    if (anim) {
      this.animTimer = setTimeout(() => {
        this.stage.classList.remove("is-animating");
        this.positionPopover();
      }, 360);
    } else {
      this.positionPopover();
    }
  }

  onResize() {
    if (!this.circuit) return;
    const { w, h: hh } = this.viewportSize();
    const prev = this.lastSize;
    this.lastSize = { w, h: hh };
    if (w < 10 || hh < 10) return;
    if (!this.userMoved || !prev) {
      this.fit(false);
      return;
    }
    // Keep the drawing point at the centre of the view where it was.
    const cx = (prev.w / 2 - this.tx) / this.s;
    const cy = (prev.h / 2 - this.ty) / this.s;
    this.tx = w / 2 - cx * this.s;
    this.ty = hh / 2 - cy * this.s;
    this.clampPan();
    this.apply(false);
  }

  // --------------------------------------------------------------- popover
  togglePopover(id) {
    if (this.openTp === id) this.closePopover(true);
    else this.openPopover(id);
  }

  openPopover(id) {
    const prev = this.openTp;
    this.openTp = id;
    this.openForm = null;
    for (const t of this.tps) t.el.setAttribute("aria-expanded", String(t.id === id));
    if (prev && prev !== id) this.tps.find((t) => t.id === prev)?.el.classList.remove("is-open");
    this.tps.find((t) => t.id === id)?.el.classList.add("is-open");
    this.renderPopover(id, true);
  }

  closePopover(restoreFocus) {
    if (!this.openTp) return;
    const t = this.tps.find((x) => x.id === this.openTp);
    this.openTp = null;
    this.openForm = null;
    this.popover.hidden = true;
    clear(this.popover);
    if (t) {
      t.el.setAttribute("aria-expanded", "false");
      t.el.classList.remove("is-open");
      if (restoreFocus) t.el.focus();
    }
  }

  renderPopover(id, focusFirst) {
    const t = this.tps.find((x) => x.id === id);
    if (!t) return;
    // A re-render after an action (e.g. "Measure") must not drop keyboard focus.
    const hadFocus = this.popover.contains(document.activeElement);
    const info = t.info;
    const level = hazardLevel(info);
    const titleId = nextId("pop-title");
    const close = h("button", { type: "button", class: "btn btn-icon btn-sm", "aria-label": "Close" }, icon("close"));
    close.addEventListener("click", () => this.closePopover(true));
    const canAct = this.sessionActive && this.handlers.canAct();
    const pendingKey = this.pending && !this.pending.blocked ? this.pending.key : null;

    let hazardNote = null;
    if (level !== "lv") {
      const nmax = Number(info.normal_max_v);
      const worst = Number(info.worst_case_v);
      let text;
      if (level === "hv") {
        text = Number.isFinite(nmax)
          ? `High voltage: about ${Math.round(nmax)} V DC in normal operation${Number.isFinite(worst) && worst > nmax + 1 ? `, up to ${Math.round(worst)} V under a fault` : ""}. Measure hands-off.`
          : "High voltage. Measure hands-off.";
      } else if (level === "hv_under_fault") {
        text = Number.isFinite(worst)
          ? `Normally low voltage, but a fault can put up to ${Math.round(worst)} V DC here. Treat it as live high voltage.`
          : "A fault can put high voltage here. Treat it as live high voltage.";
      } else {
        text = "Hazard unknown: treat this point as live high voltage.";
      }
      hazardNote = h("p", { class: `pop-hazard hz-${level}` }, icon(level === "hv" ? "bolt" : "alert"), h("span", {}, text));
    }

    const list = h("ul", { class: "pop-list" });
    for (const m of info.measurements || []) {
      const reading = this.readings.find((r) => r.key === m.key);
      const isNext = m.key === pendingKey;
      const li = h("li", { class: `pop-meas${isNext ? " is-next" : ""}` },
        h("div", { class: "pop-meas-head" },
          h("span", { class: "pop-meas-label" }, m.label),
          isNext ? h("span", { class: "chip chip-accent" }, "Recommended") : null,
          h("code", { class: "pop-key" }, m.key)),
        h("div", { class: "pop-meas-inst" }, m.instrument));
      if (reading) {
        li.append(h("p", { class: "pop-recorded" }, icon("check"),
          h("span", {}, "Recorded "), h("b", { class: "num" }, reading.text),
          h("span", { class: "muted" }, ` · step ${reading.step}`)));
      } else if (this.sessionActive) {
        const measureBtn = h("button", { type: "button", class: "btn btn-primary btn-sm", disabled: !canAct },
          icon("probe"), h("span", {}, "Measure (simulated bench)"));
        const enterBtn = h("button", {
          type: "button", class: "btn btn-secondary btn-sm", disabled: !canAct,
          "aria-expanded": String(this.openForm === m.key),
        }, icon("pencil"), h("span", {}, "Enter reading"));
        const err = h("p", { class: "form-error" });
        measureBtn.addEventListener("click", async () => {
          const res = await this.handlers.measure(m.key, measureBtn);
          if (res) err.textContent = res;
        });
        const actions = h("div", { class: "pop-actions" }, measureBtn, enterBtn);
        li.append(actions, err);
        const showForm = () => {
          const f = readingForm({
            key: m.key,
            kind: m.kind,
            onSubmit: (value, btn) => this.handlers.enterReading(m.key, value, btn),
            onCancel: () => {
              this.openForm = null;
              f.form.remove();
              enterBtn.setAttribute("aria-expanded", "false");
              enterBtn.focus();
            },
          });
          li.append(f.form);
          enterBtn.setAttribute("aria-expanded", "true");
          return f;
        };
        enterBtn.addEventListener("click", () => {
          if (this.openForm === m.key) return;
          this.openForm = m.key;
          const f = showForm();
          this.positionPopover();
          f.focus();
        });
        if (this.openForm === m.key) showForm();
      }
      list.append(li);
    }

    replaceChildren(this.popover,
      h("div", { class: "pop-head" },
        h("div", {},
          h("h3", { class: "pop-title", id: titleId }, `${info.id} · ${info.name}`),
          h("p", { class: "pop-sub" }, stageName(info.stage, this.circuit))),
        close),
      hazardNote,
      info.hint ? h("p", { class: "pop-hint" }, info.hint) : null,
      list,
      this.sessionActive ? null
        : h("p", { class: "pop-note" }, icon("info"), h("span", {}, "Start a unit to take readings at this point.")));
    this.popover.setAttribute("aria-labelledby", titleId);
    this.popover.hidden = false;
    this.positionPopover();
    if (focusFirst || (hadFocus && !this.popover.contains(document.activeElement))) {
      const first = this.popover.querySelector(".pop-actions button:not([disabled])") || close;
      first.focus({ preventScroll: true });
    }
  }

  positionPopover() {
    if (!this.openTp || this.popover.hidden) return;
    const t = this.tps.find((x) => x.id === this.openTp);
    if (!t) return;
    const { w, h: hh } = this.viewportSize();
    const cx = this.tx + t.x * this.s;
    const cy = this.ty + t.y * this.s;
    const pw = this.popover.offsetWidth;
    const ph = this.popover.offsetHeight;
    const gap = this.ringDiameter() / 2 + 12;
    let left;
    let top = clamp(cy - ph / 2, 8, Math.max(8, hh - ph - 8));
    if (cx + gap + pw <= w - 8) {
      left = cx + gap; // right of the point
    } else if (cx - gap - pw >= 8) {
      left = cx - gap - pw; // left of the point
    } else {
      // no room at either side (narrow panel): centre it and go below or above the point
      left = clamp(cx - pw / 2, 8, Math.max(8, w - pw - 8));
      top = cy + gap + ph <= hh - 8 ? cy + gap : Math.max(8, cy - gap - ph);
    }
    this.popover.style.left = `${Math.round(left)}px`;
    this.popover.style.top = `${Math.round(top)}px`;
    const inView = cx > -20 && cy > -20 && cx < w + 20 && cy < hh + 20;
    this.popover.classList.toggle("is-detached", !inView);
  }
}

