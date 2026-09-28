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

/** Discharge check: the measured voltage across the main filter capacitor. */
export function dischargeForm({ onSubmit }) {
  const inputId = nextId("dc-in");
  const errId = nextId("dc-err");
  const input = h("input", {
    type: "text", id: inputId, class: "input input-num", inputmode: "decimal",
    autocomplete: "off", placeholder: "0.8", "aria-describedby": errId,
  });
  const err = h("p", { class: "form-error", id: errId });
  const submit = h("button", { type: "submit", class: "btn btn-danger btn-sm" },
    icon("unlock"), h("span", {}, "Confirm discharge"));
  const form = h("form", { class: "discharge-form", novalidate: true },
    h("label", { for: inputId, class: "discharge-label" },
      "Voltage measured across the main filter capacitor"),
    h("div", { class: "rf-row" }, input, h("span", { class: "unit-fixed" }, "V"), submit),
    err);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const v = parseNumber(input.value);
    if (!Number.isFinite(v)) {
      err.textContent = "Enter the voltage you measured, for example 0.8.";
      input.setAttribute("aria-invalid", "true");
      input.focus();
      return;
    }
    input.removeAttribute("aria-invalid");
    err.textContent = "";
    const res = await onSubmit(v, submit);
    if (res) {
      err.textContent = res;
      input.focus();
    }
  });
  return { form, input };
}
