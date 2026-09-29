// Repair-ticket modal: verdict, belief at close, evidence table, actions, safety,
// provenance, draft/signed status, sign-off, and .md/.json downloads (Blob).

import { h, icon, replaceChildren, nextId, busyButton } from "./dom.js";
import { renderMarkdown } from "./markdown.js";
import {
  KIND_SHORT, capitalize, fmtCost, fmtNum, kindOf, pct, sourceLabel, sourceTitle, targetOf,
} from "./format.js";

function download(filename, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = h("a", { href: url, download: filename, class: "sr-only" });
  document.body.append(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 1000);
}

export class TicketDialog {
  /** handlers: load() -> Promise<ticket>, signoff(name) -> Promise<ticket>, sessionId() */
  constructor(dialog, handlers) {
    this.dialog = dialog;
    this.handlers = handlers;
    this.ticket = null;
    this.tab = "summary";
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) this.close(); // click on the backdrop
    });
    dialog.addEventListener("close", () => {
      if (this.returnFocus) this.returnFocus.focus();
    });
  }

  close() {
    if (this.dialog.open) this.dialog.close();
  }

  async open(returnFocus) {
    this.returnFocus = returnFocus || document.activeElement;
    this.tab = "summary";
    replaceChildren(this.dialog, h("div", { class: "tk-loading", role: "status" },
      h("span", { class: "spinner", "aria-hidden": "true" }), "Building the repair ticket…"));
    if (!this.dialog.open) this.dialog.showModal();
    try {
      this.ticket = await this.handlers.load();
      this.render();
    } catch (e) {
      replaceChildren(this.dialog,
        h("div", { class: "tk-loading is-error", role: "alert" }, icon("alert"),
          h("span", {}, `The ticket could not be built: ${e.message}`),
          h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: () => this.close() }, "Close")));
    }
  }

  render() {
    const t = this.ticket;
    if (!t) return;
    const titleId = "ticket-title";
    const signed = Boolean(t.signoff);
    const closeBtn = h("button", { type: "button", class: "btn btn-icon", "aria-label": "Close the ticket" }, icon("close"));
    closeBtn.addEventListener("click", () => this.close());
    const status = signed
      ? h("span", { class: "status-badge is-signed" }, icon("check"), `Signed off by ${t.signoff.by}`)
      : h("span", { class: "status-badge is-draft" }, icon("pencil"), "Draft · awaiting sign-off");

    const tabIds = { summary: nextId("tk-tab"), markdown: nextId("tk-tab") };
    const panelId = nextId("tk-panel");
    const tabBtn = (id, label) => {
      const b = h("button", {
        type: "button", role: "tab", id: tabIds[id], class: "tk-tab",
        "aria-selected": String(this.tab === id), "aria-controls": panelId, tabindex: this.tab === id ? "0" : "-1",
      }, label);
      b.addEventListener("click", () => {
        this.tab = id;
        this.render();
        this.dialog.querySelector(`#${tabIds[id]}`)?.focus();
      });
      b.addEventListener("keydown", (e) => {
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          e.preventDefault();
          this.tab = this.tab === "summary" ? "markdown" : "summary";
          this.render();
          this.dialog.querySelector(`#${tabIds[this.tab]}`)?.focus();
        }
      });
      return b;
    };
    const tabs = h("div", { class: "tk-tabs", role: "tablist", "aria-label": "Ticket view" },
      tabBtn("summary", "Summary"), tabBtn("markdown", "Markdown"));

    const body = h("div", {
      class: "tk-body", id: panelId, role: "tabpanel", "aria-labelledby": tabIds[this.tab], tabindex: "0",
    }, this.tab === "summary" ? this.summary(t) : h("div", { class: "md tk-md" }, renderMarkdown(t.markdown, { headingBase: 3 })));

    replaceChildren(this.dialog,
      h("div", { class: "tk" },
        h("header", { class: "tk-head" },
          h("div", { class: "tk-titles" },
            h("p", { class: "kicker" }, "Repair ticket"),
            h("h2", { id: titleId, class: "tk-title" }, t.circuit ? t.circuit.name : "Repair ticket"),
            h("p", { class: "tk-created num" }, [t.created, signed ? `signed ${t.signoff.at}` : null].filter(Boolean).join(" · "))),
          status,
          closeBtn),
        tabs,
        body,
        this.footer(t)));
  }

  summary(t) {
    const out = [];
    const confident = Boolean(t.confident);
    out.push(h("section", { class: `tk-verdict ${confident ? "is-confident" : "is-open"}` },
      icon(confident ? "check" : "info"),
      h("div", {},
        h("p", { class: `tk-verdict-text${String(t.verdict || "").length > 110 ? " is-long" : ""}` }, t.verdict),
        h("p", { class: "tk-verdict-sub num" },
          `${confident ? "Confident" : "Not conclusive"} · stop reason: ${t.stop_reason || "–"} · effort ${fmtNum(t.effort_spent, 1)}`))));
    if (t.ai_disclosure) out.push(h("p", { class: "muted tk-ai" }, String(t.ai_disclosure)));
    if ((t.complaint_symptoms || []).length) {
      out.push(h("p", { class: "tk-symptoms" }, h("span", { class: "mini-title" }, "Reported symptoms"),
        t.complaint_symptoms.map((sy) => h("span", { class: "chip" }, String(sy).replace(/_/g, " ")))));
    }
    const groups = t.top_groups || [];
    out.push(h("h3", { class: "tk-h" }, "Belief at close"));
    out.push(h("ol", { class: "tk-groups" }, groups.map((g) => h("li", { class: "tk-group" },
      h("div", { class: "bar-text" },
        h("span", { class: "bar-names" },
          h("span", { class: "bar-label" }, capitalize((g.faults || []).map((f) => f.label).join(" or "))),
          (g.faults || []).length > 1 ? h("span", { class: "bar-sub tk-group-sub" }, `${g.faults.length} faults that no measurement can tell apart; a lift test separates them`) : null),
        h("span", { class: "bar-pct num" }, pct(g.probability))),
      h("div", { class: "bar-track", "aria-hidden": "true" },
        h("div", { class: "bar-fill", style: { "--p": String(g.probability), "--c": g.group === -1 ? "var(--ink-3)" : "var(--accent-bar)" } }))))));
    out.push(h("p", { class: "tk-unmodeled num" }, "Probability that no single-fault model fits: ", h("b", {}, pct(t.unmodeled_probability)), "."));

    out.push(h("h3", { class: "tk-h" }, "Evidence"));
    const rs = t.readings || [];
    out.push(rs.length
      ? h("div", { class: "table-wrap" }, h("table", { class: "data-table" },
        h("caption", { class: "sr-only" }, "Evidence: readings in the order they were taken"),
        h("thead", {}, h("tr", {},
          h("th", { scope: "col", class: "num" }, "Step"), h("th", { scope: "col" }, "Measurement"),
          h("th", { scope: "col", class: "num" }, "Reading"), h("th", { scope: "col" }, "Source"),
          h("th", { scope: "col", class: "num" }, "Cost"))),
        h("tbody", {}, rs.map((r) => h("tr", {},
          h("td", { class: "num" }, String(r.step)),
          h("td", { title: r.key }, h("span", { class: "meas-target" }, targetOf(r.key)),
            h("span", { class: "meas-kind" }, ` ${kindOf(r.key) === "lift" ? "lift test" : KIND_SHORT[kindOf(r.key)] || r.what}`),
            h("span", { class: "meas-name" }, r.what)),
          h("td", { class: "num reading-val" }, r.text),
          h("td", { class: "src", title: sourceTitle(r.source) }, sourceLabel(r.source)),
          h("td", { class: "num" }, fmtCost(r.cost)))))))
      : h("p", { class: "empty-note" }, "No readings were taken."));

    if ((t.actions || []).length) {
      out.push(h("h3", { class: "tk-h" }, "Recommended action"));
      out.push(h("ul", { class: "tk-list" }, t.actions.map((a) => h("li", {}, a))));
    }
    if ((t.safety || []).length) {
      out.push(h("section", { class: "tk-safety" }, icon("bolt"),
        h("div", {}, h("h3", { class: "tk-h" }, "Safety"),
          h("ul", { class: "tk-list" }, t.safety.map((sf) => h("li", {}, sf))))));
    }
    const g = t.grounding;
    if (g) {
      const bad = (g.ungrounded || []).length;
      out.push(h("p", { class: `tk-ground${bad ? " is-bad" : ""}` }, icon(bad ? "alert" : "check"),
        bad ? `Grounding check: ${bad} number${bad === 1 ? "" : "s"} not found in the session evidence (${g.ungrounded.join(", ")}).`
          : `Grounding check: all ${g.checked} numbers in this ticket come from the session's evidence.`));
    }
    const p = t.provenance;
    if (p) {
      out.push(h("p", { class: "tk-prov" },
        `Differential ${p.differential_version} · likelihood ${p.likelihood} · policy ${p.policy} · symptom extractor ${p.extractor}. ${p.note}`));
    }
    return out;
  }

  footer(t) {
    const sid = this.handlers.sessionId() || "session";
    const base = `ticket_${(t.circuit && t.circuit.id) || "circuit"}_${sid}`;
    const statusLine = t.signoff
      ? `\n\n---\nStatus: signed off by ${t.signoff.by} at ${t.signoff.at}.\n`
      : "\n\n---\nStatus: draft - awaiting technician sign-off.\n";
    const mdBtn = h("button", { type: "button", class: "btn btn-secondary btn-sm" }, icon("download"), h("span", {}, "Download .md"));
    mdBtn.addEventListener("click", () => download(`${base}.md`, `${t.markdown}${statusLine}`, "text/markdown;charset=utf-8"));
    const jsonBtn = h("button", { type: "button", class: "btn btn-secondary btn-sm" }, icon("download"), h("span", {}, "Download .json"));
    jsonBtn.addEventListener("click", () => download(`${base}.json`, `${JSON.stringify(t, null, 2)}\n`, "application/json"));

    let sign;
    if (t.signoff) {
      sign = h("p", { class: "tk-signed" }, icon("check"),
        h("span", {}, "Signed off by ", h("b", {}, t.signoff.by), ` at ${t.signoff.at}.`));
    } else {
      const nameId = nextId("tk-name");
      const input = h("input", {
        id: nameId, class: "input", type: "text", autocomplete: "name", placeholder: "Your name", maxlength: "80",
      });
      const btn = h("button", { type: "submit", class: "btn btn-primary btn-sm" }, icon("check"), h("span", {}, "Sign off"));
      const err = h("p", { class: "form-error" });
      sign = h("form", { class: "tk-sign", novalidate: true },
        h("label", { for: nameId }, "Technician"), input, btn, err);
      sign.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (btn.classList.contains("is-busy")) return;
        const name = input.value.trim();
        if (!name) {
          err.textContent = "Enter your name to sign the ticket off.";
          input.focus();
          return;
        }
        err.textContent = "";
        const restore = busyButton(btn);
        try {
          this.ticket = await this.handlers.signoff(name);
          this.render();
          this.dialog.querySelector(".tk-signed")?.setAttribute("tabindex", "-1");
          this.dialog.querySelector(".tk-signed")?.focus();
        } catch (ex) {
          restore();
          err.textContent = `Sign-off failed: ${ex.message}`;
        }
      });
    }
    return h("footer", { class: "tk-foot" }, sign, h("div", { class: "tk-downloads" }, mdBtn, jsonBtn));
  }
}

