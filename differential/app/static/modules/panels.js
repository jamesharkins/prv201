// Right-column panels: safety banner, next-measurement card, readings table.

import { h, icon, clear, replaceChildren, nextId } from "./dom.js";
import {
  KIND_SHORT, capitalize, fmtCost, fmtNum, kindOf, pct, sourceLabel, sourceTitle, stageName, targetOf,
} from "./format.js";
import { approvalForm, dischargeForm, guessForm, liftForm, readingForm, supervisorForm } from "./forms.js";

/** Bold the "Label:" lead of a safety line ("Hands-off measurement: ..."). */
function leadEmphasis(line) {
  const m = String(line).match(/^([A-Z][^:.]{2,40}):\s+(.*)$/s);
  if (!m) return [line];
  return [h("strong", {}, `${m[1]}:`), ` ${m[2]}`];
}

// ------------------------------------------------------------------ banner
export class SafetyBanner {
  /** handlers.discharge(readings, button) and handlers.approve(note, button)
   *  -> Promise<string> (error text or ""). update() returns true when the banner changed. */
  constructor(slot, handlers) {
    this.slot = slot;
    this.handlers = handlers;
    this.sig = null;
  }

  update(state) {
    const b = state && state.banner;
    const pending = state && state.pending;
    const blocked = Boolean(pending && pending.blocked === "discharge_verification");
    const approval = Boolean(pending && pending.blocked === "owner_approval");
    const supervised = Boolean(pending && pending.blocked === "supervisor");
    if (!b) {
      this.sig = null;
      clear(this.slot);
      return false;
    }
    const sig = JSON.stringify([b.title, b.lines, blocked, approval, pending && pending.key,
      state.discharge_readings]);
    if (sig === this.sig) return false;
    this.sig = sig;
    const titleId = nextId("banner-title");
    const lines = Array.isArray(b.lines) ? b.lines : [];
    const body = h("div", { class: "banner-body" },
      h("h2", { class: "banner-title", id: titleId }, b.title || "High voltage"),
      lines.length ? h("ul", { class: "banner-list" }, lines.map((l) => h("li", {}, leadEmphasis(l)))) : null);
    if (blocked) {
      const f = dischargeForm({
        points: pending.discharge_points || [], readings: state.discharge_readings || {},
        onSubmit: (v, btn) => this.handlers.discharge(v, btn),
      });
      body.append(h("div", { class: "banner-lock" },
        h("p", { class: "banner-lock-text" }, icon("lock"),
          h("span", {}, `Removing ${pending.part || "this part"} stays locked until every listed point reads below 2 V. The readings are recorded on the ticket as your attestation; the tool cannot check them.`)),
        f.form));
    }
    if (approval) {
      const f = approvalForm({ part: pending.part, onSubmit: (n, btn) => this.handlers.approve(n, btn) });
      body.append(h("div", { class: "banner-lock" }, f.form));
    }
    if (supervised) {
      const f = supervisorForm({ onSubmit: (n, btn) => this.handlers.supervisor(n, btn) });
      body.append(h("div", { class: "banner-lock" }, f.form));
    }
    const level = b.level === "danger" ? "danger" : "warning";
    replaceChildren(this.slot,
      h("section", { class: `banner banner-${level}`, "aria-labelledby": titleId },
        h("div", { class: "banner-icon", "aria-hidden": "true" }, icon(blocked || approval || supervised ? "lock" : "bolt")),
        body));
    return true; // a new or changed banner
  }
}

// -------------------------------------------------------- next measurement
export class NextCard {
  /**
   * handlers: measure(key, btn), enterReading(key, value, btn), openTicket(), focusChat(),
   *           focusDischarge(), canAct()
   */
  constructor(root, handlers) {
    this.root = root;
    this.handlers = handlers;
    this.key = null;
    this.whyOpen = false;
    this.formOpen = false;
  }

  update(state, circuit) {
    const hadFocus = this.root.contains(document.activeElement);
    this.render(state, circuit);
    // After an action taken from this card, keep keyboard focus in the card.
    if (hadFocus && !this.root.contains(document.activeElement)) {
      const target = this.root.querySelector(".next-actions button:not([disabled])");
      if (target) target.focus({ preventScroll: true });
    }
  }

  render(state, circuit) {
    const pending = state.pending;
    const b = state.belief || {};
    const started = (state.history || []).length > 0 || (state.readings || []).length > 0;
    const key = pending ? `${pending.key}|${pending.blocked || ""}|${pending.withheld ? "w" : ""}`
      : `none|${b.would_stop}|${started}`;
    if (key !== this.key) {
      this.key = key;
      this.whyOpen = false;
      this.formOpen = false;
    }
    const canAct = this.handlers.canAct();
    const head = (extra) => h("div", { class: "panel-head" },
      h("h2", { class: "panel-title", id: "next-title" }, "Next measurement"), extra);
    this.root.classList.remove("is-done", "is-locked", "is-hv", "is-idle", "is-warning");

    if (!pending) {
      if (!started) {
        this.root.classList.add("is-idle");
        replaceChildren(this.root, head(null),
          h("p", { class: "next-what" }, "Start with the complaint"),
          h("p", { class: "next-how" },
            "Describe what the unit does wrong in the chat below. Differential reads the complaint, sets its prior over the faults and recommends the first measurement."),
          h("div", { class: "next-actions" },
            h("button", { type: "button", class: "btn btn-secondary", onclick: () => this.handlers.focusChat() },
              icon("chat"), h("span", {}, "Write the complaint"))));
        return;
      }
      const top = (b.ranked_groups || [])[0];
      const names = top ? (top.faults || []).map((f) => f.label).join(" or ") : "";
      let title;
      let text;
      const unmodeled = Boolean(top && top.group === -1);
      if (b.would_stop && b.stop_reason === "confident") {
        title = top && top.group === -1 ? "Stopped: no single fault fits" : "Diagnosis ready";
        text = top && top.group === -1
          ? `The readings fit no single-fault model (${pct(top.probability)}). The ticket lists the evidence for a manual investigation.`
          : `${names} (${pct(top ? top.probability : 0)}). Open the ticket for the evidence trail and sign it off.`;
      } else if (b.would_stop) {
        title = "Stopped";
        text = `${b.stop_reason === "budget" ? "The effort budget is used up." : "No measurement is left to take."}${names ? ` Best explanation so far: ${names} (${pct(top.probability)}).` : ""}`;
      } else {
        title = "No measurement pending";
        text = "Ask Differential for the next step in the chat, or click a test point to measure it.";
      }
      this.root.classList.add(unmodeled ? "is-warning" : "is-done");
      replaceChildren(this.root, head(null),
        h("p", { class: "next-what" }, icon(unmodeled ? "alert" : b.would_stop ? "check" : "info", "next-what-icon"), title),
        h("p", { class: "next-how" }, text),
        b.would_stop ? h("div", { class: "next-actions" },
          h("button", { type: "button", class: "btn btn-primary", onclick: () => this.handlers.openTicket() },
            icon("ticket"), h("span", {}, "Open repair ticket"))) : null);
      return;
    }

    const kind = kindOf(pending.key);
    const cost = h("span", { class: "chip num", title: "Effort units for this step" }, `Cost ${fmtCost(pending.cost)}`);
    const bits = Number(pending.expected_information_bits);
    const info = Number.isFinite(bits)
      ? h("span", { class: "chip num", title: "Expected information from this measurement" }, `${fmtNum(bits, 2)} bits`)
      : null;

    if (pending.withheld) {
      const f = guessForm({ options: pending.options || [], onSubmit: (k, btn) => this.handlers.guess(k, btn) });
      replaceChildren(this.root,
        head(h("div", { class: "chips" }, h("span", { class: "chip" }, icon("pencil"), "Trainee mode"))),
        h("p", { class: "next-how" }, "The recommendation stays hidden until you commit your own choice; then both are shown and recorded."),
        f.form);
      return;
    }
    if (pending.blocked === "supervisor") {
      this.root.classList.add("is-locked");
      replaceChildren(this.root,
        head(h("div", { class: "chips" }, h("span", { class: "chip chip-danger" }, icon("lock"), "Needs a supervisor"))),
        h("p", { class: "next-how" }, String(pending.next_step || "")),
        h("div", { class: "next-actions" },
          h("button", { type: "button", class: "btn btn-danger-outline", onclick: () => this.handlers.focusDischarge() },
            icon("unlock"), h("span", {}, "Name the supervisor"))));
      return;
    }
    if (pending.blocked === "owner_approval") {
      this.root.classList.add("is-locked");
      replaceChildren(this.root,
        head(h("div", { class: "chips" }, h("span", { class: "chip chip-danger" }, icon("lock"), "Needs approval"), cost)),
        h("p", { class: "next-what" }, `${capitalize(pending.what)}: `, h("b", {}, pending.part || targetOf(pending.key))),
        h("p", { class: "next-how" }, String(pending.next_step || "").replace(/\s*\(approve_part_removal\)/g, "")),
        h("div", { class: "next-actions" },
          h("button", { type: "button", class: "btn btn-secondary", onclick: () => this.handlers.focusDischarge() },
            icon("pencil"), h("span", {}, "Record the owner's approval"))));
      return;
    }
    if (pending.blocked === "discharge_verification") {
      this.root.classList.add("is-locked");
      replaceChildren(this.root,
        head(h("div", { class: "chips" }, h("span", { class: "chip chip-danger" }, icon("lock"), "Locked"), cost)),
        h("p", { class: "next-what" }, `${capitalize(pending.what)}: `, h("b", {}, pending.part || targetOf(pending.key))),
        // The server names its internal tool in parentheses; the technician does not need it.
        h("p", { class: "next-how" }, String(pending.next_step || "").replace(/\s*\(confirm_discharge\)/g, "")),
        h("div", { class: "next-actions" },
          h("button", { type: "button", class: "btn btn-danger-outline", onclick: () => this.handlers.focusDischarge() },
            icon("unlock"), h("span", {}, "Enter the discharge readings"))));
      return;
    }

    const tp = pending.test_point && circuit
      ? (circuit.test_points || []).find((x) => x.id === pending.test_point) : null;
    const hv = Boolean(pending.high_voltage);
    if (hv) this.root.classList.add("is-hv");
    const what = h("p", { class: "next-what" },
      kind === "lift" ? `${capitalize(pending.what)}: ` : `${capitalize(pending.what)} at `,
      h("b", {}, pending.test_point || pending.part || targetOf(pending.key)));
    const sub = tp ? h("p", { class: "next-where" },
      h("span", { class: "next-tpname" }, tp.name), ` · ${stageName(tp.stage, circuit)}`) : null;
    const how = h("p", { class: "next-how" }, h("span", { class: "label" }, "How "), pending.how || "");

    const measureBtn = h("button", { type: "button", class: "btn btn-primary", disabled: !canAct },
      icon("probe"), h("span", {}, "Measure (simulated)"));
    const enterBtn = h("button", {
      type: "button", class: "btn btn-secondary", disabled: !canAct, "aria-expanded": String(this.formOpen),
    }, icon("pencil"), h("span", {}, kind === "lift" ? "Enter result" : "Enter reading"));
    const err = h("p", { class: "form-error" });
    const formSlot = h("div", { class: "next-form" });
    measureBtn.addEventListener("click", async () => {
      err.textContent = "";
      const res = await this.handlers.measure(pending.key, measureBtn);
      if (res) err.textContent = res;
    });
    const openForm = (focus) => {
      this.formOpen = true;
      enterBtn.setAttribute("aria-expanded", "true");
      const close = () => {
        this.formOpen = false;
        clear(formSlot);
        enterBtn.setAttribute("aria-expanded", "false");
        enterBtn.focus();
      };
      const f = kind === "lift"
        ? liftForm({ part: pending.part, onSubmit: (v, btn) => this.handlers.enterReading(pending.key, v, btn), onCancel: close })
        : readingForm({ key: pending.key, kind, onSubmit: (v, btn) => this.handlers.enterReading(pending.key, v, btn), onCancel: close });
      replaceChildren(formSlot, f.form);
      if (focus) f.focus();
    };
    enterBtn.addEventListener("click", () => {
      if (this.formOpen) return;
      openForm(true);
    });
    if (this.formOpen) openForm(false);

    const why = this.renderWhy(pending, kind);
    replaceChildren(this.root,
      head(h("div", { class: "chips" },
        hv ? h("span", { class: "chip chip-danger" }, icon("bolt"), "High voltage") : null,
        info, cost)),
      what, sub, how,
      h("div", { class: "next-actions" }, measureBtn, enterBtn),
      err, formSlot, why);
  }

  renderWhy(p, kind) {
    const details = h("details", { class: "why" });
    details.open = this.whyOpen;
    details.addEventListener("toggle", () => { this.whyOpen = details.open; });
    const bits = Number(p.expected_information_bits) || 0;
    const cost = Number(p.cost) || 1;
    const perCost = p.policy === "eig_per_cost";
    const options = [{ key: p.key, what: p.what, bits, cost, chosen: true },
      ...(p.alternatives || []).map((a) => ({
        key: a.key, what: a.what, bits: Number(a.information_bits) || 0, cost: Number(a.cost) || 1, chosen: false,
      }))];
    const score = (o) => (perCost ? o.bits / o.cost : o.bits);
    const maxScore = Math.max(1e-9, ...options.map(score));
    const unit = perCost ? "bits per effort unit" : "bits";
    const rows = options.map((o) => h("li", { class: `opt${o.chosen ? " is-chosen" : ""}` },
      h("div", { class: "opt-text" },
        h("span", { class: "opt-key" }, `${KIND_SHORT[kindOf(o.key)] || kindOf(o.key)} ${targetOf(o.key)}`),
        o.chosen ? h("span", { class: "chip chip-accent chip-xs" }, "chosen") : null,
        h("span", { class: "opt-val num" }, `${fmtNum(score(o), 2)}`),
        h("span", { class: "opt-detail num" }, `${fmtNum(o.bits, 2)} bits · cost ${fmtCost(o.cost)}`)),
      h("div", { class: "opt-track", "aria-hidden": "true" },
        h("div", { class: "opt-fill", style: { "--p": String(score(o) / maxScore) } }))));

    const preds = (p.expected_readings || []).map((e) => h("tr", {},
      h("th", { scope: "row" }, e.label),
      h("td", { class: "num" }, pct(e.probability)),
      h("td", { class: "num" }, typeof e.predicted === "string" ? e.predicted : (e.range_text || e.predicted_text || fmtNum(e.predicted, 4)))));

    details.append(
      h("summary", {}, icon("chevron", "why-chevron"), h("span", {}, "Why this?")),
      h("div", { class: "why-body" },
        h("p", { class: "why-lede" },
          `Expected information: `, h("b", { class: "num" }, `${fmtNum(bits, 2)} bits`),
          ` for an effort of ${fmtCost(cost)}.`,
          perCost ? " Differential picks the measurement with the most expected information per unit of effort." : ""),
        h("p", { class: "mini-title" }, `Options compared (${unit})`),
        h("ol", { class: "opts" }, rows),
        preds.length ? h("p", { class: "mini-title" }, kind === "lift" ? "What each leading suspect predicts" : "Expected reading per leading suspect (95 % range)") : null,
        preds.length ? h("div", { class: "table-wrap" }, h("table", { class: "pred-table" },
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Suspect"), h("th", { scope: "col", class: "num" }, "Now"),
            h("th", { scope: "col", class: "num" }, "Predicts"))),
          h("tbody", {}, preds))) : null));
    return details;
  }
}

// ---------------------------------------------------------------- readings
export class ReadingsTable {
  constructor(root) {
    this.root = root;
    this.count = 0;
    this.metaEl = h("span", { class: "panel-meta num" });
    this.body = h("div", { class: "readings-body" });
    replaceChildren(root,
      h("div", { class: "panel-head" },
        h("h2", { class: "panel-title", id: "readings-title" }, "Readings"), this.metaEl),
      this.body);
  }

  update(state, circuit) {
    const rs = [...(state.readings || [])].sort((a, b) => a.step - b.step);
    const spent = rs.reduce((acc, r) => acc + (Number(r.cost) || 0), 0);
    this.metaEl.textContent = rs.length ? `${rs.length} · effort ${fmtNum(spent, 1)}` : "";
    const grew = rs.length > this.count;
    this.count = rs.length;
    if (!rs.length) {
      replaceChildren(this.body, h("p", { class: "empty-note" },
        "No readings yet. Use Measure on the recommended step, or click a test point on the schematic."));
      return;
    }
    const latest = rs[rs.length - 1].step;
    const tpName = (id) => {
      const tp = circuit && (circuit.test_points || []).find((x) => x.id === id);
      return tp ? tp.name : "";
    };
    const rows = rs.map((r) => {
      const kind = kindOf(r.key);
      const target = targetOf(r.key);
      return h("tr", { class: grew && r.step === latest ? "is-new" : null },
        h("td", { class: "num" }, String(r.step)),
        h("td", { title: r.key },
          h("span", { class: "meas-target" }, target),
          h("span", { class: "meas-kind" }, ` ${kind === "lift" ? "lift test" : KIND_SHORT[kind] || kind}`),
          tpName(target) ? h("span", { class: "meas-name" }, tpName(target)) : null),
        h("td", { class: "num reading-val" }, r.text),
        h("td", { class: "src", title: sourceTitle(r.source) }, sourceLabel(r.source)),
        h("td", { class: "num" }, fmtCost(r.cost)));
    });
    replaceChildren(this.body, h("div", { class: "table-wrap" },
      h("table", { class: "data-table" },
        h("caption", { class: "sr-only" }, "Readings taken in this session"),
        h("thead", {}, h("tr", {},
          h("th", { scope: "col", class: "num" }, "Step"),
          h("th", { scope: "col" }, "Measurement"),
          h("th", { scope: "col", class: "num" }, "Reading"),
          h("th", { scope: "col" }, "Source"),
          h("th", { scope: "col", class: "num" }, "Cost"))),
        h("tbody", {}, rows))));
  }
}
