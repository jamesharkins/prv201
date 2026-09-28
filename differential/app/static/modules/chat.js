// Chat panel: transcript (user / assistant / event turns), composer, quick
// prompts, and the meter-photo flow (upload -> proposal -> technician confirms).

import { h, icon, clear, replaceChildren, nextId } from "./dom.js";
import { renderMarkdown } from "./markdown.js";
import { KIND_SHORT, fmtTime, kindOf, pct, targetOf } from "./format.js";
import { parseNumber } from "./forms.js";

export const EXAMPLE_COMPLAINT = "The channel hums and sounds thin";
const UNIT_SCALE = { mV: 1e-3, V: 1, "Ω": 1, kΩ: 1e3, MΩ: 1e6 };

export class ChatPanel {
  /**
   * handlers: send(text) -> Promise<string>, uploadPhoto(file) -> Promise<{photo_id, proposal}>,
   *           confirmPhoto(pid, key, value, btn) -> Promise<string>, canAct()
   */
  constructor(root, handlers) {
    this.root = root;
    this.handlers = handlers;
    this.rendered = []; // signatures of rendered turns
    this.state = null;
    this.circuit = null;
    this.photo = null;
    this.build();
  }

  build() {
    clear(this.root);
    this.modeEl = h("span", { class: "panel-meta" });
    this.log = h("div", {
      class: "transcript", role: "log", "aria-live": "polite", "aria-relevant": "additions",
      "aria-label": "Conversation with Differential", tabindex: "0",
    });
    this.typing = h("div", { class: "msg msg-assistant typing", hidden: true, "aria-hidden": "true" },
      h("span", { class: "dot" }), h("span", { class: "dot" }), h("span", { class: "dot" }),
      h("span", { class: "typing-text" }, "Differential is working…"));
    this.photoSlot = h("div", { class: "photo-slot" });
    this.chips = h("div", { class: "quick", role: "group", "aria-label": "Suggested messages" });
    const inputId = nextId("chat-input");
    this.input = h("textarea", {
      id: inputId, class: "input composer-input", rows: "1",
      placeholder: `Describe the complaint, e.g. “${EXAMPLE_COMPLAINT}”`,
      autocomplete: "off",
    });
    this.file = h("input", { type: "file", accept: "image/*", class: "sr-only", tabindex: "-1", "aria-hidden": "true" });
    this.photoBtn = h("button", {
      type: "button", class: "btn btn-icon", "aria-label": "Upload a meter photo", title: "Upload a meter photo",
    }, icon("camera"));
    this.sendBtn = h("button", { type: "submit", class: "btn btn-primary btn-send", "aria-label": "Send message" },
      icon("send"), h("span", { class: "btn-text" }, "Send"));
    this.form = h("form", { class: "composer" },
      h("label", { class: "sr-only", for: inputId }, "Message to Differential"),
      this.input, this.file, this.photoBtn, this.sendBtn);
    this.root.append(
      h("div", { class: "panel-head" }, h("h2", { class: "panel-title", id: "chat-title" }, "Conversation"), this.modeEl),
      this.log, this.photoSlot, this.chips, this.form);

    this.form.addEventListener("submit", (e) => {
      e.preventDefault();
      this.submit();
    });
    this.input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        this.submit();
      }
    });
    this.input.addEventListener("input", () => this.autosize());
    this.photoBtn.addEventListener("click", () => this.file.click());
    this.file.addEventListener("change", () => {
      const f = this.file.files && this.file.files[0];
      this.file.value = "";
      if (f) this.startPhoto(f);
    });
  }

  autosize() {
    this.input.style.height = "auto";
    this.input.style.height = `${Math.min(120, this.input.scrollHeight)}px`;
  }

  focusInput() {
    this.input.focus();
  }

  setBusy(busy, label = "Differential is working…") {
    this.typing.hidden = !busy;
    this.typing.querySelector(".typing-text").textContent = label;
    if (busy) {
      this.log.append(this.typing);
      this.scrollToEnd(true);
    }
  }

  async submit() {
    const text = this.input.value.trim();
    if (!text || !this.handlers.canAct()) return;
    this.input.value = "";
    this.autosize();
    // Optimistic echo of the technician's message while the reply is computed.
    const echo = this.renderTurn({ role: "user", text, t: Date.now() / 1000, meta: {} });
    echo.classList.add("is-pending");
    this.log.append(echo);
    this.scrollToEnd(true);
    const err = await this.handlers.send(text);
    echo.remove();
    if (err) {
      this.input.value = text;
      this.autosize();
    }
  }

  update(state, circuit) {
    if (this.sessionId && this.sessionId !== state.session_id) this.clearPhoto();
    this.sessionId = state.session_id;
    const newCircuit = this.circuit !== circuit;
    this.state = state;
    this.circuit = circuit;
    const mode = state.mode || "offline";
    this.modeEl.textContent = { offline: "Offline agent", live: "Live agent (Claude)", replay: "Replay" }[mode] || mode;
    const turns = state.transcript || [];
    const sigs = turns.map((t) => `${t.role}|${t.t}|${t.text.length}`);
    const prefixOk = !newCircuit && this.rendered.length <= sigs.length
      && this.rendered.every((sg, i) => sg === sigs[i]);
    if (!prefixOk) {
      clear(this.log);
      this.rendered = [];
    }
    const log = this.log;
    const wasNearEnd = log.scrollHeight - log.scrollTop - log.clientHeight < 160;
    const fresh = [];
    for (let i = this.rendered.length; i < turns.length; i += 1) {
      const el = this.renderTurn(turns[i]);
      fresh.push(el);
      this.log.append(el);
      this.rendered.push(sigs[i]);
    }
    if (!turns.length) {
      this.log.append(h("div", { class: "chat-empty" },
        icon("chat"),
        h("p", {}, "The first message is the technician’s complaint: what the unit does wrong, in your own words.")));
    } else {
      this.log.querySelector(".chat-empty")?.remove();
    }
    if (!this.typing.hidden) this.log.append(this.typing);
    if (fresh.length && (wasNearEnd || !prefixOk)) this.revealFresh(fresh);
    this.input.placeholder = turns.some((t) => t.role === "user")
      ? "Ask “why”, report a reading (“TP9 = 254 V”), or ask for the ticket"
      : `Describe the complaint, e.g. “${EXAMPLE_COMPLAINT}”`;
    this.renderChips(state);
    if (this.photo && this.photo.proposalShown) this.refreshPhotoKeys();
  }

  /** Bring new turns into view, starting from the first new one so a long reply is read from its top. */
  revealFresh(fresh) {
    const log = this.log;
    const first = fresh.find((el) => !el.classList.contains("msg-user")) || fresh[0];
    const target = Math.min(first.offsetTop - 8, log.scrollHeight - log.clientHeight);
    log.scrollTo({ top: Math.max(0, target), behavior: "auto" });
  }

  scrollToEnd(force) {
    const el = this.log;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
    if (force || near) el.scrollTo({ top: el.scrollHeight, behavior: force ? "auto" : "smooth" });
  }

  renderChips(state) {
    const hasUser = (state.transcript || []).some((t) => t.role === "user");
    const chip = (label, text) => {
      const b = h("button", { type: "button", class: "chip-btn" }, label);
      b.addEventListener("click", () => {
        if (!this.handlers.canAct()) return;
        this.input.value = text;
        this.submit();
      });
      return b;
    };
    const items = [];
    if (!hasUser) {
      const b = h("button", { type: "button", class: "chip-btn" }, `Use example: “${EXAMPLE_COMPLAINT}”`);
      b.addEventListener("click", () => {
        this.input.value = EXAMPLE_COMPLAINT;
        this.autosize();
        this.input.focus();
      });
      items.push(b);
    } else if (state.pending && !state.pending.blocked) {
      items.push(chip("Why this measurement?", "Why this measurement?"));
    }
    replaceChildren(this.chips, items);
    this.chips.hidden = !items.length;
  }

  renderTurn(t) {
    if (t.role === "event") {
      return h("div", { class: "msg msg-event" }, icon("probe"), h("span", {}, t.text));
    }
    if (t.role === "user") {
      const body = h("div", { class: "msg-bubble" });
      String(t.text).split("\n").forEach((line, i) => {
        if (i) body.append(h("br"));
        body.append(line);
      });
      return h("div", { class: "msg msg-user" },
        h("div", { class: "msg-meta" }, h("span", { class: "msg-name" }, "Technician"),
          h("time", {}, fmtTime(t.t))),
        body);
    }
    const meta = t.meta || {};
    const body = h("div", { class: "msg-body md" }, renderMarkdown(t.text, { headingBase: 4 }));
    for (const p of body.querySelectorAll("p")) {
      const txt = p.textContent || "";
      if (/^(HIGH VOLTAGE|Before lifting)/.test(txt)) p.classList.add("msg-hv");
    }
    const foot = [];
    if (meta.refused) {
      foot.push(h("span", { class: "chip chip-warning" }, icon("shield"), `Refused by the safety screen (${String(meta.refused).replace(/_/g, " ")})`));
    }
    if (meta.fallback) {
      foot.push(h("span", { class: "chip", title: `Fallback reason: ${meta.fallback}` },
        "Offline reply: no live or recorded model answer"));
    }
    const g = meta.grounding;
    if (g && Number(g.checked) > 0) {
      const bad = (g.ungrounded || []).length;
      foot.push(bad
        ? h("span", { class: "ground ground-bad" }, icon("alert"), `${bad} ungrounded number${bad === 1 ? "" : "s"} removed`)
        : h("span", { class: "ground" }, icon("check"), `${g.checked} number${Number(g.checked) === 1 ? "" : "s"} checked against the evidence`));
    }
    return h("div", { class: "msg msg-assistant" },
      h("div", { class: "msg-meta" }, h("span", { class: "msg-name" }, "Differential"), h("time", {}, fmtTime(t.t))),
      body,
      foot.length ? h("div", { class: "msg-foot" }, foot) : null);
  }

  // ----------------------------------------------------------------- photo
  async startPhoto(file) {
    this.clearPhoto();
    const url = URL.createObjectURL(file);
    const status = h("p", { class: "photo-status" }, h("span", { class: "spinner", "aria-hidden": "true" }), "Reading the meter display…");
    const bodyEl = h("div", { class: "photo-body" }, h("p", { class: "photo-title" }, "Meter photo"), status);
    const discard = h("button", { type: "button", class: "btn btn-icon btn-sm photo-close", "aria-label": "Discard the photo" }, icon("close"));
    discard.addEventListener("click", () => this.clearPhoto());
    const card = h("section", { class: "photo-card", "aria-label": "Meter photo reading" },
      h("img", { class: "photo-thumb", src: url, alt: "The uploaded meter photo" }), bodyEl, discard);
    this.photo = { url, card, bodyEl, pid: null, proposal: null, proposalShown: false };
    this.photoSlot.append(card);
    let res;
    try {
      res = await this.handlers.uploadPhoto(file);
    } catch (e) {
      replaceChildren(status, icon("alert"), `The photo could not be read: ${e.message}`);
      status.classList.add("is-error");
      return;
    }
    if (!this.photo || this.photo.card !== card) return;
    if (!res) {
      this.clearPhoto();
      return;
    }
    this.photo.pid = res.photo_id;
    this.photo.proposal = res.proposal || {};
    this.showProposal();
  }

  clearPhoto() {
    if (!this.photo) return;
    URL.revokeObjectURL(this.photo.url);
    this.photo.card.remove();
    this.photo = null;
  }

  measurementOptions() {
    const st = this.state || {};
    const taken = new Set((st.readings || []).map((r) => r.key));
    const groups = [];
    for (const tp of (this.circuit && this.circuit.test_points) || []) {
      const ms = (tp.measurements || []).filter((m) => !taken.has(m.key));
      if (ms.length) groups.push({ tp, ms });
    }
    return groups;
  }

  refreshPhotoKeys() {
    const sel = this.photo && this.photo.keySelect;
    if (!sel) return;
    const cur = sel.value;
    this.fillKeys(sel, cur);
  }

  fillKeys(sel, preferred) {
    clear(sel);
    sel.append(h("option", { value: "" }, "Choose the measurement…"));
    const groups = this.measurementOptions();
    for (const g of groups) {
      const og = h("optgroup", { label: `${g.tp.id} · ${g.tp.name}` });
      for (const m of g.ms) og.append(h("option", { value: m.key }, `${m.key} · ${m.label}`));
      sel.append(og);
    }
    const keys = groups.flatMap((g) => g.ms.map((m) => m.key));
    sel.value = preferred && keys.includes(preferred) ? preferred : "";
    return keys;
  }

  showProposal() {
    const p = this.photo.proposal || {};
    const st = this.state || {};
    const kids = [h("p", { class: "photo-title" }, "Proposed reading from the photo")];
    const err = p.error || (p.legible === false ? "The display could not be read." : "");
    const val = Number(p.value);
    const hasValue = p.value !== null && p.value !== undefined && Number.isFinite(val);
    if (err) {
      kids.push(h("p", { class: "photo-error" }, icon("alert"), h("span", {}, `The reader reported an error: ${err}`)));
    }
    if (hasValue || p.text) {
      const conf = Number(p.confidence);
      kids.push(h("p", { class: "photo-value" },
        h("b", { class: "num" }, `${p.text || val} ${p.unit || ""}`.trim()),
        p.mode ? h("span", { class: "muted" }, ` · ${p.mode}`) : null,
        Number.isFinite(conf) ? h("span", { class: "muted" }, ` · confidence ${pct(conf)}`) : null,
        p.source ? h("span", { class: "muted" }, ` · ${p.source === "offline" ? "offline reader" : p.source === "claude" ? "Claude vision" : p.source}`) : null));
    } else if (!err) {
      kids.push(h("p", { class: "photo-error" }, icon("alert"), h("span", {}, "No value was read from this photo. Type the value you see on the meter.")));
    }
    if (p.note) kids.push(h("p", { class: "muted" }, String(p.note)));
    const issues = [...(Array.isArray(p.issues) ? p.issues : []),
      ...(p.plausibility && Array.isArray(p.plausibility.issues) ? p.plausibility.issues : [])];
    if (issues.length) {
      kids.push(h("ul", { class: "photo-issues" }, issues.map((i) => h("li", {}, String(i).replace(/^[a-z_]+:\s*/, "")))));
    }
    if (p.plausibility && p.plausibility.suggestion) {
      kids.push(h("p", { class: "muted" }, String(p.plausibility.suggestion)));
    }

    // Confirmation form: pick the measurement key and confirm or edit the value.
    const keyId = nextId("photo-key");
    const valId = nextId("photo-val");
    const keySelect = h("select", { id: keyId, class: "input", required: true });
    // Preselect the recommended measurement only when the meter function fits it
    // (DC volts for a DC step, AC volts for hum); otherwise the technician picks.
    const pendingKey = st.pending && !st.pending.blocked ? st.pending.key : null;
    const fits = { DC: ["dc"], AC: ["hum"] }[p.mode] || [];
    const preselect = pendingKey && fits.includes(kindOf(pendingKey)) ? pendingKey : "";
    const keys = this.fillKeys(keySelect, preselect);
    this.photo.keySelect = keySelect;
    let base = Number(p.base_value);
    if (!Number.isFinite(base) && hasValue) base = val * (UNIT_SCALE[p.unit] ?? 1);
    const valueInput = h("input", {
      id: valId, class: "input input-num", type: "text", inputmode: "decimal", autocomplete: "off",
      value: Number.isFinite(base) ? String(Number(base.toPrecision(6))) : "",
    });
    const unitEl = h("span", { class: "unit-fixed" });
    const setUnit = () => {
      const kind = kindOf(keySelect.value);
      unitEl.textContent = { dc: "V", hum: "V", ac: "V/V", ac20: "V/V", ac20k: "V/V", thd: "%" }[kind] || "";
    };
    setUnit();
    keySelect.addEventListener("change", setUnit);
    const formErr = h("p", { class: "form-error" });
    const confirm = h("button", { type: "submit", class: "btn btn-primary btn-sm", disabled: !keys.length },
      icon("check"), h("span", {}, "Confirm and record"));
    const discard = h("button", { type: "button", class: "btn btn-ghost btn-sm" }, "Discard");
    discard.addEventListener("click", () => this.clearPhoto());
    const form = h("form", { class: "photo-form", novalidate: true },
      h("div", { class: "photo-fields" },
        h("label", { for: keyId }, "Measurement"), keySelect,
        h("label", { for: valId }, "Value to record"), h("div", { class: "rf-row" }, valueInput, unitEl)),
      h("p", { class: "photo-note" }, icon("info"),
        h("span", {}, "Nothing is recorded until you confirm. Check the value and the unit against the meter.")),
      h("div", { class: "rf-row" }, confirm, discard),
      formErr);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const v = parseNumber(valueInput.value);
      if (!Number.isFinite(v)) {
        formErr.textContent = "Enter the value in the unit shown, for example 15.1.";
        valueInput.focus();
        return;
      }
      if (!keySelect.value) {
        formErr.textContent = "Choose which measurement this photo shows.";
        return;
      }
      formErr.textContent = "";
      const res = await this.handlers.confirmPhoto(this.photo.pid, keySelect.value, v, confirm);
      if (res) formErr.textContent = res;
      else this.clearPhoto();
    });
    kids.push(form);
    replaceChildren(this.photo.bodyEl, kids);
    this.photo.proposalShown = true;
    (hasValue && !keySelect.value ? keySelect : valueInput).focus();
  }
}

export function kindLabel(key) {
  const k = kindOf(key);
  return `${KIND_SHORT[k] || k} ${targetOf(key)}`;
}
