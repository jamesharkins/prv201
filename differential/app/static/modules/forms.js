// Reading entry forms shared by the schematic popover, the next-measurement card,
// the discharge check and the photo confirmation.

import { h, icon, nextId } from "./dom.js";
import { BASE_UNIT, KIND_UNITS, toBase, validateReading } from "./format.js";

/** Parse a typed number; accepts a decimal comma and exponent notation. */
export function parseNumber(text) {
  const t = String(text ?? "").trim().replace(/\s+/g, "").replace(",", ".");
  if (!/^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i.test(t)) return NaN;
  return Number(t);
}

/**
 * A one-line "value + unit + Record" form for a measurement kind.
 * onSubmit(baseValue, submitButton) must return a promise resolving to an error
 * string (shown under the field) or "" on success.
 */
export function readingForm({ key, kind, onSubmit, onCancel, submitLabel = "Record", initial = "" }) {
  const inputId = nextId("rf-in");
  const errId = nextId("rf-err");
  const units = KIND_UNITS[kind] || [BASE_UNIT[kind] || ""];
  const input = h("input", {
    type: "text",
    id: inputId,
    class: "input input-num",
    inputmode: "decimal",
    autocomplete: "off",
    spellcheck: "false",
    placeholder: { dc: "15.1", hum: "2.1", thd: "0.12" }[kind] || "0.98",
    "aria-describedby": errId,
    value: initial,
  });
  const unitEl = units.length > 1
    ? h("select", { class: "input input-unit", "aria-label": "Unit" },
      units.map((u) => h("option", { value: u }, u)))
    : h("span", { class: "unit-fixed" }, units[0] || "");
  const err = h("p", { class: "form-error", id: errId });
  const submit = h("button", { type: "submit", class: "btn btn-primary btn-sm" }, submitLabel);
  const cancel = onCancel
    ? h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: onCancel }, "Cancel")
    : null;
  const form = h("form", { class: "reading-form", novalidate: true },
    h("label", { class: "sr-only", for: inputId }, `Reading for ${key}`),
    h("div", { class: "rf-row" }, input, unitEl, submit, cancel),
    err);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const raw = parseNumber(input.value);
    const unit = unitEl.tagName === "SELECT" ? unitEl.value : units[0];
    const base = toBase(raw, unit);
    const msg = Number.isFinite(raw) ? validateReading(kind, base) : "Enter a number, for example 15.1.";
    if (msg) {
      err.textContent = msg;
      input.setAttribute("aria-invalid", "true");
      input.focus();
      return;
    }
    err.textContent = "";
    input.removeAttribute("aria-invalid");
    const result = await onSubmit(base, submit);
    if (result) {
      err.textContent = result;
      input.focus();
    }
  });
  return { form, input, focus: () => input.focus() };
}

/** Out-of-circuit (lift) test result: two buttons, 1 = out of tolerance, 0 = within. */
export function liftForm({ part, onSubmit, onCancel }) {
  const err = h("p", { class: "form-error" });
  const make = (label, value, cls) => {
    const b = h("button", { type: "button", class: `btn ${cls} btn-sm` }, label);
    b.addEventListener("click", async () => {
      const res = await onSubmit(value, b);
      err.textContent = res || "";
    });
    return b;
  };
  const row = h("div", { class: "rf-row", role: "group", "aria-label": `Result of the ${part} test` },
    make("Out of tolerance", 1, "btn-secondary"),
    make("Within tolerance", 0, "btn-secondary"),
    onCancel ? h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: onCancel }, "Cancel") : null);
  const wrap = h("div", { class: "reading-form" }, row, err);
  return { form: wrap, focus: () => row.querySelector("button")?.focus() };
}

/** Discharge check: one reading per point that can hold high voltage. Part removal stays
 *  locked until every point reads below the limit; the readings are the technician's
 *  attestation and go on the ticket. */
export function dischargeForm({ points = [], readings = {}, onSubmit }) {
  const errId = nextId("dc-err");
  const err = h("p", { class: "form-error", id: errId });
  const inputs = points.map((p) => {
    const id = nextId("dc-in");
    const input = h("input", {
      type: "text", id, class: "input input-num", inputmode: "decimal", autocomplete: "off",
      placeholder: "0.3", "aria-describedby": errId, "data-tp": p.tp,
      value: readings[p.tp] !== undefined ? String(readings[p.tp]) : "",
    });
    return { tp: p.tp, input, row: h("div", { class: "rf-row dc-row" },
      h("label", { for: id, class: "dc-tp" }, h("b", {}, p.tp), h("span", { class: "dc-name" }, ` ${p.name || ""}`)),
      input, h("span", { class: "unit-fixed" }, "V")) };
  });
  const submit = h("button", { type: "submit", class: "btn btn-danger btn-sm" },
    icon("unlock"), h("span", {}, "Record discharge readings"));
  const form = h("form", { class: "discharge-form", novalidate: true },
    h("p", { class: "discharge-label" },
      "Measured voltage at each point that can hold high voltage (each must be below 2 V):"),
    ...inputs.map((x) => x.row), h("div", { class: "rf-row" }, submit), err);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const out = {};
    for (const x of inputs) {
      const v = parseNumber(x.input.value);
      if (!Number.isFinite(v)) {
        err.textContent = `Enter the voltage you measured at ${x.tp}, for example 0.3.`;
        x.input.setAttribute("aria-invalid", "true");
        x.input.focus();
        return;
      }
      x.input.removeAttribute("aria-invalid");
      out[x.tp] = v;
    }
    err.textContent = "";
    const res = await onSubmit(out, submit);
    if (res) {
      err.textContent = res;
      inputs[0]?.input.focus();
    }
  });
  return { form, input: inputs[0] ? inputs[0].input : null };
}

/** Owner's approval before a part is removed from the board (a destructive step). */
export function approvalForm({ part, onSubmit }) {
  const id = nextId("appr");
  const box = h("input", { type: "checkbox", id, class: "approval-box" });
  const err = h("p", { class: "form-error" });
  const submit = h("button", { type: "submit", class: "btn btn-secondary btn-sm" },
    icon("pencil"), h("span", {}, "Record approval"));
  const form = h("form", { class: "approval-form", novalidate: true },
    h("div", { class: "rf-row" }, box,
      h("label", { for: id }, `The owner agrees that parts, starting with ${part || "this part"}, may be removed from this unit for testing.`)),
    h("div", { class: "rf-row" }, submit), err);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!box.checked) {
      err.textContent = "Tick the box once the owner has agreed.";
      box.focus();
      return;
    }
    err.textContent = "";
    const res = await onSubmit("owner agreed that parts may be removed for testing", submit);
    if (res) err.textContent = res;
  });
  return { form, input: box };
}


/** Trainee mode: the supervising technician's name (high-voltage units). */
export function supervisorForm({ onSubmit }) {
  const id = nextId("sup");
  const input = h("input", { type: "text", id, class: "input", autocomplete: "name",
    placeholder: "Supervising technician" });
  const err = h("p", { class: "form-error" });
  const submit = h("button", { type: "submit", class: "btn btn-danger btn-sm" },
    icon("unlock"), h("span", {}, "Record supervisor"));
  const form = h("form", { class: "supervisor-form", novalidate: true },
    h("label", { for: id, class: "discharge-label" },
      "A qualified technician must supervise in person. Their name goes on the ticket:"),
    h("div", { class: "rf-row" }, input, submit), err);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!input.value.trim()) {
      err.textContent = "Enter the supervising technician's name.";
      input.focus();
      return;
    }
    err.textContent = "";
    const res = await onSubmit(input.value.trim(), submit);
    if (res) err.textContent = res;
  });
  return { form, input };
}

/** Trainee mode: the trainee commits their own next measurement before seeing the tool's. */
export function guessForm({ options = [], onSubmit }) {
  const id = nextId("guess");
  const select = h("select", { id, class: "input guess-select" },
    h("option", { value: "" }, "Choose a measurement…"),
    ...options.map((o) => h("option", { value: o.key },
      `${o.test_point || o.part || o.key}: ${o.what}`)));
  const err = h("p", { class: "form-error" });
  const submit = h("button", { type: "submit", class: "btn btn-primary btn-sm" },
    icon("pencil"), h("span", {}, "Commit my choice"));
  const form = h("form", { class: "guess-form", novalidate: true },
    h("label", { for: id, class: "discharge-label" }, "Your call first: which measurement would you take next?"),
    h("div", { class: "rf-row" }, select, submit), err);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!select.value) {
      err.textContent = "Choose the measurement you would take next.";
      select.focus();
      return;
    }
    err.textContent = "";
    const res = await onSubmit(select.value, submit);
    if (res) err.textContent = res;
  });
  return { form, input: select };
}
