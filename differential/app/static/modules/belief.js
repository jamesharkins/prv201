// Belief panel: animated horizontal bars for the top hypotheses (colour = the
// suspect part's circuit stage, text in ink colours), the probability that no
// single-fault model fits (hatched, shown apart), a step-by-step history chart of
// the top suspect's probability, and an effort meter.

import { h, s, icon, clear, replaceChildren, prefersReducedMotion } from "./dom.js";
import {
  faultPart, partDescription, pct, stageColor, stageName, fmtNum, KIND_SHORT, kindOf,
} from "./format.js";

const MAX_ROWS = 6;
const EASE_MS = 650;

function faultStage(fault, circuit) {
  const part = faultPart(fault, circuit);
  return part ? part.stage : null;
}

function barColor(fault, circuit) {
  if (fault === "healthy") return "var(--neutral-mark)";
  const st = faultStage(fault, circuit);
  return st ? stageColor(st) : "var(--neutral-mark)";
}

/** Tween the number shown in `el` from its current value to `to` (probability). */
function tweenPct(el, to) {
  const from = Number(el.dataset.value);
  el.dataset.value = String(to);
  if (!Number.isFinite(from) || prefersReducedMotion() || Math.abs(from - to) < 0.004) {
    el.textContent = pct(to);
    return;
  }
  const t0 = performance.now();
  const step = (now) => {
    const k = Math.min(1, (now - t0) / EASE_MS);
    const e = 1 - (1 - k) ** 3;
    el.textContent = pct(from + (to - from) * e);
    if (k < 1 && el.dataset.value === String(to)) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

export class BeliefPanel {
  constructor(root) {
    this.root = root;
    this.rows = new Map(); // fault -> row element
    this.build();
  }

  build() {
    clear(this.root);
    this.metaEl = h("span", { class: "panel-meta num" });
    this.revealEl = h("div", { class: "reveal-callout", hidden: true, role: "status" });
    this.emptyEl = h("p", { class: "empty-note", hidden: true });
    this.list = h("ol", { class: "bars", "aria-label": "Most likely faults" });
    this.groupNote = h("p", { class: "group-note", hidden: true });
    this.unmodeled = h("div", { class: "bar-row bar-unmodeled" });
    this.legend = h("div", { class: "stage-legend", "aria-label": "Bar colour shows the stage of the suspect part" });
    this.history = h("figure", { class: "history" });
    this.lastHistory = null;
    if (window.ResizeObserver) {
      let lastW = 0;
      new ResizeObserver(() => {
        const w = Math.round(this.history.clientWidth);
        if (w && w !== lastW && this.lastHistory) {
          lastW = w;
          requestAnimationFrame(() => this.renderHistory(...this.lastHistory));
        }
      }).observe(this.history);
    }
    this.meter = h("div", { class: "meter" });
    this.note = h("p", { class: "belief-note" });
    this.root.append(
      h("div", { class: "panel-head" },
        h("h2", { class: "panel-title", id: "belief-title" }, "Belief"),
        this.metaEl),
      this.revealEl,
      this.emptyEl,
      this.list,
      this.groupNote,
      this.unmodeled,
      this.legend,
      h("div", { class: "belief-foot" }, this.history, this.meter),
      this.note);
  }

  update(state, circuit) {
    const b = state.belief || {};
    const hyps = (state.top_hypotheses || []).filter((x) => x.fault !== "unmodeled");
    const started = (state.history || []).length > 0 || (state.readings || []).length > 0;
    const measured = b.measurements_taken ?? (state.readings || []).length;
    const bits = Number(b.entropy_bits);
    this.metaEl.textContent = `${measured} measurement${measured === 1 ? "" : "s"}` +
      (Number.isFinite(bits) ? ` · uncertainty ${fmtNum(bits, 2)} bits` : "");

    this.renderReveal(state, hyps);
    const rows = window.innerHeight <= 800 && window.innerWidth > 900 ? 5 : MAX_ROWS;
    if (!started) {
      this.emptyEl.hidden = false;
      this.emptyEl.textContent =
        "Every fault starts equally likely. Describe the complaint in the chat to set the prior.";
      this.list.hidden = true;
      this.legend.hidden = true;
      this.unmodeled.hidden = true;
      this.groupNote.hidden = true;
    } else {
      this.emptyEl.hidden = true;
      this.list.hidden = false;
      this.legend.hidden = false;
      this.unmodeled.hidden = false;
      const shown = hyps.slice(0, rows);
      const groups = this.groupTags(shown, b.ranked_groups || []);
      this.renderBars(shown, circuit, state.revealed, groups);
      this.renderGroupNote(groups);
      this.renderUnmodeled(Number(b.unmodeled_probability) || 0);
      this.renderLegend(shown, circuit);
    }
    this.renderHistory(state.history || [], circuit);
    this.renderMeter(b);
    const thr = Number(b.stop_threshold);
    const top = (b.ranked_groups || [])[0];
    const stopText = Number.isFinite(thr)
      ? `The engine stops when one fault, or one group of faults that no measurement can tell apart, reaches ${pct(thr)}`
      : "";
    const lead = top ? (top.group === -1 ? `No single-fault model fits: ${pct(top.probability)}.`
      : `Leading ${(top.faults || []).length > 1 ? "group" : "suspect"}: ${pct(top.probability)}.`) : "";
    if (b.would_stop && b.stop_reason) {
      const why = { confident: "confident", budget: "effort budget used", exhausted: "no measurement left" }[b.stop_reason] || b.stop_reason;
      this.note.textContent = `Stopped (${why}). ${lead}`.trim();
    } else {
      this.note.textContent = stopText
        ? `${stopText}${top && started ? ` (now ${pct(top.probability)})` : ""}.`
        : "";
    }
  }

  renderReveal(state, hyps) {
    const rv = state.revealed;
    if (!rv) {
      this.revealEl.hidden = true;
      clear(this.revealEl);
      return;
    }
    const idx = hyps.findIndex((x) => x.fault === rv.fault);
    const groups = (state.belief && state.belief.ranked_groups) || [];
    const inTopGroup = groups.length && (groups[0].faults || []).some((f) => f.fault === rv.fault);
    let verdict;
    let cls;
    if (idx === 0 || inTopGroup) {
      verdict = idx === 0 ? "It is the leading suspect." : "It is in the leading group of faults that readings cannot separate.";
      cls = "is-match";
    } else if (idx > 0) {
      verdict = `It ranks #${idx + 1} (${pct(hyps[idx].p)}).`;
      cls = "is-miss";
    } else {
      verdict = "It is not among the top suspects.";
      cls = "is-miss";
    }
    this.revealEl.className = `reveal-callout ${cls}`;
    replaceChildren(this.revealEl,
      icon(cls === "is-match" ? "check" : "info"),
      h("div", {},
        h("p", { class: "reveal-title" }, "Hidden fault (demo): ", h("b", {}, rv.label)),
        h("p", { class: "reveal-sub" }, verdict)));
    this.revealEl.hidden = false;
  }

  /** Letters for the nontrivial ambiguity groups among the shown suspects. */
  groupTags(shown, ranked) {
    const tags = new Map(); // fault -> {letter, size, p}
    const letters = "ABCDEFGH";
    let n = 0;
    for (const g of ranked) {
      const faults = (g.faults || []).map((f) => f.fault);
      if (g.group < 0 || faults.length < 2) continue;
      if (!shown.some((x) => faults.includes(x.fault))) continue;
      const tag = { letter: letters[n] || "?", size: faults.length, p: g.probability };
      n += 1;
      for (const f of faults) tags.set(f, tag);
    }
    return tags;
  }

  renderGroupNote(tags) {
    const seen = [];
    for (const t of tags.values()) if (!seen.includes(t)) seen.push(t);
    if (!seen.length) {
      this.groupNote.hidden = true;
      return;
    }
    replaceChildren(this.groupNote,
      seen.slice(0, 3).map((t, i) => [i ? ", " : "",
        h("b", {}, `${i ? "group" : "Group"} ${t.letter}`), ` (${t.size} faults, ${pct(t.p)} together)`]),
      `: no measurement can tell ${seen.length > 1 ? "their members" : "its members"} apart; a lift test separates them.`);
    this.groupNote.hidden = false;
  }

  renderBars(hyps, circuit, revealed, groups = new Map()) {
    const animate = !prefersReducedMotion();
    // FLIP: remember where rows are before the update.
    const before = new Map();
    if (animate) for (const [f, el] of this.rows) before.set(f, el.getBoundingClientRect().top);
    const keep = new Set(hyps.map((x) => x.fault));
    for (const [f, el] of this.rows) {
      if (!keep.has(f)) {
        el.remove();
        this.rows.delete(f);
      }
    }
    hyps.forEach((x, i) => {
      let row = this.rows.get(x.fault);
      const isNew = !row;
      if (isNew) {
        row = this.makeRow(x, circuit);
        this.rows.set(x.fault, row);
        if (animate) row.classList.add("is-entering");
      }
      const fill = row.querySelector(".bar-fill");
      const pctEl = row.querySelector(".bar-pct");
      fill.style.setProperty("--p", String(Math.max(0, Math.min(1, x.p))));
      tweenPct(pctEl, x.p);
      row.classList.toggle("is-top", i === 0);
      row.classList.toggle("is-true", Boolean(revealed && revealed.fault === x.fault));
      row.querySelector(".bar-true").hidden = !(revealed && revealed.fault === x.fault);
      const tag = groups.get(x.fault);
      const gEl = row.querySelector(".bar-group");
      gEl.hidden = !tag;
      gEl.textContent = tag ? `group ${tag.letter}` : "";
      gEl.title = tag ? `One of ${tag.size} faults that no measurement can tell apart` : "";
      row.setAttribute("aria-label", `${x.label}: ${pct(x.p)}`);
      this.list.append(row); // append in rank order (moves existing rows)
    });
    if (!animate) return;
    for (const [f, el] of this.rows) {
      const old = before.get(f);
      if (old === undefined) {
        requestAnimationFrame(() => el.classList.remove("is-entering"));
        continue;
      }
      const dy = old - el.getBoundingClientRect().top;
      if (Math.abs(dy) < 1) continue;
      el.style.transition = "none";
      el.style.transform = `translateY(${dy}px)`;
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          el.style.transition = "";
          el.style.transform = "";
        });
      });
    }
  }

  makeRow(x, circuit) {
    const part = faultPart(x.fault, circuit);
    const sub = x.fault === "healthy" ? "unit within tolerance"
      : part ? `${partDescription(part)} · ${stageName(part.stage, circuit)}` : "";
    return h("li", { class: "bar-row", dataset: { fault: x.fault } },
      h("div", { class: "bar-text" },
        h("span", { class: "bar-names" },
          h("span", { class: "bar-label" }, x.fault === "healthy" ? "No fault" : x.label),
          h("span", { class: "chip chip-xs bar-group", hidden: true }),
          sub ? h("span", { class: "bar-sub" }, sub) : null,
          h("span", { class: "bar-true", hidden: true }, icon("check"), "hidden fault")),
        h("span", { class: "bar-pct num" })),
      h("div", { class: "bar-track", "aria-hidden": "true" },
        h("div", { class: "bar-fill", style: { "--c": barColor(x.fault, circuit), "--p": "0" } })));
  }

  renderUnmodeled(p) {
    const warn = p >= 0.2;
    let pctEl = this.unmodeled.querySelector(".bar-pct");
    if (!pctEl) {
      replaceChildren(this.unmodeled,
        h("div", { class: "bar-text" },
          h("span", { class: "bar-names" },
            h("span", { class: "bar-label" }, "No single-fault model fits"),
            h("span", { class: "bar-sub" }, "e.g. two faults or a modification"),
            h("span", { class: "bar-warn", hidden: true }, icon("alert"), "check by hand")),
          h("span", { class: "bar-pct num" })),
        h("div", { class: "bar-track", "aria-hidden": "true" },
          h("div", { class: "bar-fill bar-fill-hatch", style: { "--p": "0" } })));
      pctEl = this.unmodeled.querySelector(".bar-pct");
    }
    this.unmodeled.classList.toggle("is-warning", warn);
    this.unmodeled.querySelector(".bar-warn").hidden = !warn;
    this.unmodeled.querySelector(".bar-fill").style.setProperty("--p", String(Math.max(0, Math.min(1, p))));
    this.unmodeled.setAttribute("aria-label", `No single-fault model fits: ${pct(p)}`);
    tweenPct(pctEl, p);
  }

  renderLegend(hyps, circuit) {
    const seen = [];
    for (const x of hyps) {
      const st = faultStage(x.fault, circuit);
      if (st && !seen.includes(st)) seen.push(st);
    }
    replaceChildren(this.legend,
      h("span", { class: "stage-legend-title" }, "Stage"),
      seen.map((st) => h("span", { class: "stage-item" },
        h("span", { class: "swatch", style: { "--c": stageColor(st) }, "aria-hidden": "true" }),
        stageName(st, circuit))),
      hyps.some((x) => x.fault === "healthy")
        ? h("span", { class: "stage-item" },
          h("span", { class: "swatch", style: { "--c": "var(--neutral-mark)" }, "aria-hidden": "true" }),
          "No fault")
        : null);
  }

  renderHistory(history, circuit) {
    this.lastHistory = [history, circuit];
    clear(this.history);
    const cap = h("figcaption", { class: "mini-title" }, "Top suspect by step");
    this.history.append(cap);
    if (!history.length) {
      this.history.append(h("p", { class: "mini-empty" }, "Appears after the complaint."));
      return;
    }
    const W = Math.max(160, Math.round(this.history.clientWidth) || 280);
    const H = 64;
    const padL = 26;
    const padR = 34;
    const padT = 6;
    const padB = 14;
    const n = history.length;
    const maxStep = Math.max(1, ...history.map((x) => x.step));
    const x = (st) => padL + (maxStep ? (st / maxStep) : 0) * (W - padL - padR);
    const y = (p) => padT + (1 - p) * (H - padT - padB);
    const pts = history.map((snap) => {
      const top = (snap.top || []).find((x) => x.fault !== "unmodeled") || { p: 0, label: "", fault: "" };
      return { step: snap.step, label: snap.label, p: top.p, who: top.label, fault: top.fault };
    });
    const svg = s("svg", {
      class: "history-svg", viewBox: `0 0 ${W} ${H}`, width: W, height: H,
      role: "img",
      "aria-label": `Top suspect probability by step: ${pts.map((p) => `step ${p.step} ${pct(p.p)}`).join(", ")}`,
    });
    for (const g of [0, 0.5, 1]) {
      svg.append(s("line", { class: g === 0 ? "axis" : "grid", x1: padL, x2: W - padR, y1: y(g), y2: y(g) }));
      svg.append(s("text", { class: "tick", x: padL - 4, y: y(g) + 3, "text-anchor": "end" }, g === 1 ? "100%" : `${g * 100}`));
    }
    const d = pts.map((p, i) => `${i ? "L" : "M"}${x(p.step).toFixed(1)},${y(p.p).toFixed(1)}`).join(" ");
    if (n > 1) svg.append(s("path", { class: "history-line", d }));
    const tip = h("div", { class: "chart-tip", hidden: true, role: "presentation" });
    pts.forEach((p, i) => {
      const cx = x(p.step);
      const cy = y(p.p);
      const g = s("g", { class: "history-pt" });
      g.append(s("circle", { class: "hit", cx, cy, r: 11 }));
      g.append(s("circle", { class: "dot", cx, cy, r: 4, style: `fill: ${p.fault === "unmodeled" ? "var(--ink-3)" : barColor(p.fault, circuit)}` }));
      const show = () => {
        const kind = kindOf(p.label);
        const what = p.label === "complaint" ? "after the complaint" : `after ${KIND_SHORT[kind] ? `${KIND_SHORT[kind]} at ` : ""}${p.label.split(":")[1] || p.label}`;
        replaceChildren(tip, h("b", { class: "num" }, pct(p.p)), " ", p.who || "", h("br"),
          h("span", { class: "muted" }, `Step ${p.step}, ${what}`));
        tip.hidden = false;
        const bw = svg.getBoundingClientRect().width || W;
        tip.style.left = `${Math.round((cx / W) * bw)}px`;
      };
      g.addEventListener("pointerenter", show);
      g.addEventListener("pointerleave", () => { tip.hidden = true; });
      svg.append(g);
      if (i === n - 1) {
        svg.append(s("text", { class: "end-label", x: cx + 7, y: cy + 4 }, pct(p.p)));
      }
    });
    // step labels on the x axis (first, last, and every step when there are few)
    pts.forEach((p, i) => {
      if (n <= 8 || i === 0 || i === n - 1 || i % 2 === 0) {
        svg.append(s("text", { class: "tick", x: x(p.step), y: H - 2, "text-anchor": "middle" }, String(p.step)));
      }
    });
    const wrap = h("div", { class: "history-plot" }, svg, tip);
    // Screen-reader table twin of the chart.
    const table = h("table", {},
      h("caption", {}, "Top suspect probability after each step"),
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Step"), h("th", { scope: "col" }, "After"),
        h("th", { scope: "col" }, "Top suspect"), h("th", { scope: "col" }, "Probability"))),
      h("tbody", {}, pts.map((p) => h("tr", {}, h("td", {}, String(p.step)), h("td", {}, p.label),
        h("td", {}, p.who), h("td", {}, pct(p.p))))));
    // (a table ignores a 1px width, so the visually hidden wrapper is a div)
    this.history.append(wrap, h("div", { class: "sr-only" }, table));
  }

  renderMeter(b) {
    const spent = Number(b.effort_spent) || 0;
    const budget = Number(b.effort_budget) || 0;
    const frac = budget > 0 ? Math.min(1, spent / budget) : 0;
    const level = frac >= 0.9 ? "danger" : frac >= 0.75 ? "warning" : "ok";
    let fill = this.meter.querySelector(".meter-fill");
    if (!fill) {
      this.meterValue = h("span", { class: "meter-value num" });
      fill = h("div", { class: "meter-fill" });
      this.meterTrack = h("div", {
        class: "meter-track", role: "meter", "aria-label": "Effort spent",
        "aria-valuemin": "0",
      }, fill);
      this.meterNote = h("p", { class: "meter-note" });
      replaceChildren(this.meter,
        h("div", { class: "mini-title" }, "Effort", this.meterValue),
        this.meterTrack,
        this.meterNote);
    }
    this.meterValue.textContent = budget ? `${fmtNum(spent, 1)} / ${fmtNum(budget, 1)}` : fmtNum(spent, 1);
    this.meterNote.textContent = budget ? `${fmtNum(Math.max(0, budget - spent), 1)} units left in the budget` : "";
    this.meterTrack.setAttribute("aria-valuemax", String(budget || 0));
    this.meterTrack.setAttribute("aria-valuenow", String(spent));
    this.meterTrack.setAttribute("aria-valuetext", `${fmtNum(spent, 1)} of ${fmtNum(budget, 1)} effort units`);
    this.meter.dataset.level = level;
    fill.style.setProperty("--p", String(frac));
  }
}
