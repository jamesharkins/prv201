// Small DOM helpers. Every piece of server text is inserted with textContent
// (or createTextNode); innerHTML is only used for the static icon paths below.

const SVG_NS = "http://www.w3.org/2000/svg";

function setAttrs(el, attrs, svg = false) {
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") {
      if (svg) el.setAttribute("class", v);
      else el.className = v;
    } else if (k === "text") {
      el.textContent = String(v);
    } else if (k === "dataset") {
      for (const [dk, dv] of Object.entries(v)) {
        if (dv !== null && dv !== undefined) el.dataset[dk] = String(dv);
      }
    } else if (k === "style" && typeof v === "object") {
      for (const [sk, sv] of Object.entries(v)) {
        if (sv === null || sv === undefined) continue;
        if (sk.startsWith("--")) el.style.setProperty(sk, String(sv));
        else el.style[sk] = sv;
      }
    } else if (k.startsWith("on") && typeof v === "function") {
      el.addEventListener(k.slice(2).toLowerCase(), v);
    } else if (v === true) {
      el.setAttribute(k, "");
    } else {
      el.setAttribute(k, String(v));
    }
  }
}

function appendChildren(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false || c === "") continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

/** Create an HTML element: h("button", {class: "btn", onclick}, "Label"). */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  setAttrs(el, attrs);
  appendChildren(el, children);
  return el;
}

/** Create an SVG element. */
export function s(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  setAttrs(el, attrs, true);
  appendChildren(el, children);
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function replaceChildren(el, ...children) {
  clear(el);
  appendChildren(el, children);
  return el;
}

// Static, hand-written 24x24 stroke icons (no external requests, no icon font).
const ICONS = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4"/>',
  moon: '<path d="M20.5 13.2A8.5 8.5 0 1 1 10.8 3.5a6.6 6.6 0 0 0 9.7 9.7z"/>',
  ticket: '<path d="M6 3h8.5L19 7.5V21H6z"/><path d="M14 3v5h5"/><path d="M9 12.5h6M9 16.5h6"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  fit: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  target: '<circle cx="12" cy="12" r="7.5"/><circle cx="12" cy="12" r="2.5"/><path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3"/>',
  camera: '<path d="M3.5 8h3.2l1.8-2.8h7l1.8 2.8h3.2V19H3.5z"/><circle cx="12" cy="13" r="3.4"/>',
  send: '<path d="M4 11.5L20 4l-5.5 16-3-6.5z"/><path d="M11.5 13.5L20 4"/>',
  download: '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19.5h14"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  alert: '<path d="M12 3.5L2.5 20h19z"/><path d="M12 10v4.5"/><path d="M12 17.3v.2"/>',
  bolt: '<path d="M13.5 2.5L5 13.5h6l-1 8 8.5-11h-6z"/>',
  lock: '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8.5 10.5V7.5a3.5 3.5 0 0 1 7 0v3"/>',
  unlock: '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8.5 10.5V7.5a3.5 3.5 0 0 1 6.8-1.2"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><path d="M12 7.6v.2"/>',
  probe: '<rect x="6" y="2.5" width="12" height="19" rx="2.5"/><rect x="9" y="5.5" width="6" height="4" rx="0.8"/><circle cx="12" cy="15" r="2.4"/>',
  pencil: '<path d="M4 20l1-4.5L15.5 5a2.1 2.1 0 0 1 3 3L8 18.5z"/><path d="M13.5 7l3 3"/>',
  chevron: '<path d="M9 6l6 6-6 6"/>',
  chat: '<path d="M4 5h16v11H9l-5 4z"/>',
  list: '<path d="M8 6h12M8 12h12M8 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
  spark: '<path d="M3 17l5-6 4 3 5-7 4 4"/>',
  shield: '<path d="M12 3l7.5 3v5.5c0 4.5-3.2 8-7.5 9.5-4.3-1.5-7.5-5-7.5-9.5V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
};

/** An inline SVG icon element (decorative: aria-hidden). */
export function icon(name, cls = "") {
  const el = document.createElementNS(SVG_NS, "svg");
  el.setAttribute("viewBox", "0 0 24 24");
  el.setAttribute("aria-hidden", "true");
  el.setAttribute("focusable", "false");
  el.setAttribute("class", `icon-svg${cls ? " " + cls : ""}`);
  el.innerHTML = ICONS[name] || ICONS.info;
  return el;
}

/** Replace <span class="icon" data-icon="name"> placeholders in static markup. */
export function hydrateIcons(root = document) {
  for (const span of root.querySelectorAll("span.icon[data-icon]")) {
    if (span.firstChild) continue;
    span.append(icon(span.dataset.icon));
  }
}

export function setIcon(span, name) {
  span.dataset.icon = name;
  replaceChildren(span, icon(name));
}

let announceTimer = null;
/** Polite screen-reader announcement. */
export function announce(text) {
  const el = document.getElementById("announcer");
  if (!el) return;
  el.textContent = "";
  clearTimeout(announceTimer);
  announceTimer = setTimeout(() => { el.textContent = text; }, 60);
}

/** Transient error/info toast (also read out by the assertive live region). */
export function toast(message, kind = "error", ms = 7000) {
  const host = document.getElementById("toasts");
  if (!host) return;
  const close = h("button", { type: "button", class: "toast-close", "aria-label": "Dismiss" },
    icon("close"));
  const el = h("div", { class: `toast toast-${kind}` },
    icon(kind === "error" ? "alert" : "info", "toast-icon"),
    h("div", { class: "toast-text", text: message }),
    close);
  const remove = () => {
    el.classList.add("is-leaving");
    setTimeout(() => el.remove(), 200);
  };
  close.addEventListener("click", remove);
  host.append(el);
  if (ms > 0) setTimeout(remove, ms);
}

export function prefersReducedMotion() {
  return Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
}

/** Put a button into a busy state (spinner, aria-busy, aria-disabled) and return a
 *  restore function. The button is not `disabled`, so it keeps keyboard focus; callers
 *  ignore repeated clicks while a request runs. */
export function busyButton(btn) {
  if (!btn) return () => {};
  btn.classList.add("is-busy");
  btn.setAttribute("aria-busy", "true");
  btn.setAttribute("aria-disabled", "true");
  return () => {
    btn.classList.remove("is-busy");
    btn.removeAttribute("aria-busy");
    btn.removeAttribute("aria-disabled");
  };
}

let uid = 0;
export function nextId(prefix = "id") {
  uid += 1;
  return `${prefix}-${uid}`;
}
