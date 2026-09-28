// A tiny, safe Markdown renderer for the repair ticket and assistant messages.
// It builds DOM nodes directly and inserts all text with text nodes, so any HTML
// in the source is shown literally (escaped by construction), never parsed.
// Supported: #-headings, paragraphs (single newlines become line breaks),
// "-"/"*"/"1." lists, pipe tables, "---" rules, **bold**, _italic_/*italic*, `code`.

import { h } from "./dom.js";

const INLINE = new RegExp(
  [
    "(\\*\\*([^*\\n]+?)\\*\\*)", // **bold**
    "(`([^`\\n]+)`)", // `code`
    "((?<![\\p{L}\\p{N}_])_([^_\\n]+?)_(?![\\p{L}\\p{N}_]))", // _italic_ (not snake_case)
    "((?<![\\p{L}\\p{N}*])\\*([^*\\s][^*\\n]*?)\\*(?![\\p{L}\\p{N}*]))", // *italic*
  ].join("|"),
  "gu",
);

export function renderInline(text) {
  const frag = document.createDocumentFragment();
  const src = String(text ?? "");
  let last = 0;
  for (const m of src.matchAll(INLINE)) {
    if (m.index > last) frag.append(document.createTextNode(src.slice(last, m.index)));
    if (m[1]) frag.append(h("strong", {}, renderInline(m[2])));
    else if (m[3]) frag.append(h("code", { text: m[4] }));
    else if (m[5]) frag.append(h("em", {}, renderInline(m[6])));
    else if (m[7]) frag.append(h("em", {}, renderInline(m[8])));
    last = m.index + m[0].length;
  }
  if (last < src.length) frag.append(document.createTextNode(src.slice(last)));
  return frag;
}

const RE_HEADING = /^(#{1,6})\s+(.*)$/;
const RE_RULE = /^\s*(-{3,}|\*{3,}|_{3,})\s*$/;
const RE_ITEM = /^\s*([-*+]|\d+[.)])\s+/;
const RE_TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function isTableStart(lines, i) {
  return /^\s*\|/.test(lines[i]) && i + 1 < lines.length && RE_TABLE_SEP.test(lines[i + 1]);
}

function isBlockStart(lines, i) {
  const l = lines[i];
  return RE_HEADING.test(l) || RE_RULE.test(l) || RE_ITEM.test(l) || isTableStart(lines, i);
}

function splitRow(line) {
  let t = line.trim();
  if (t.startsWith("|")) t = t.slice(1);
  if (t.endsWith("|")) t = t.slice(0, -1);
  return t.split("|").map((c) => c.trim());
}

function numericCell(text) {
  return /^[-+<>~≈]?\s*[0-9.,]+\s*(%|V|mV|µV|V\/V|dB|rms|units?)?(\s*\(.*\))?(\s*rms)?$/.test(text);
}

function table(header, rows) {
  const wrap = h("div", { class: "md-table-wrap" });
  const t = h("table", { class: "md-table" });
  // A column is numeric (right-aligned, header included) when all its cells are.
  const numeric = header.map((_, k) => rows.length > 0
    && rows.every((r) => !(r[k] ?? "").trim() || numericCell((r[k] ?? "").trim())));
  t.append(h("thead", {}, h("tr", {}, header.map((c, k) =>
    h("th", { scope: "col", class: numeric[k] ? "num" : null }, renderInline(c))))));
  const body = h("tbody");
  for (const r of rows) {
    body.append(h("tr", {}, header.map((_, k) => {
      const cell = r[k] ?? "";
      return h("td", { class: numeric[k] ? "num" : null }, renderInline(cell));
    })));
  }
  t.append(body);
  wrap.append(t);
  return wrap;
}

/**
 * Render Markdown source to a DocumentFragment.
 * headingBase: the HTML level used for "#" (e.g. 3 renders "#" as <h3>).
 */
export function renderMarkdown(source, { headingBase = 3 } = {}) {
  const frag = document.createDocumentFragment();
  const lines = String(source ?? "").replace(/\r\n?/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const hm = line.match(RE_HEADING);
    if (hm) {
      const level = Math.min(6, headingBase + hm[1].length - 1);
      frag.append(h(`h${level}`, { class: "md-h" }, renderInline(hm[2])));
      i += 1;
      continue;
    }
    if (RE_RULE.test(line)) {
      frag.append(h("hr", { class: "md-rule" }));
      i += 1;
      continue;
    }
    if (isTableStart(lines, i)) {
      const header = splitRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      frag.append(table(header, rows));
      continue;
    }
    if (RE_ITEM.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line);
      const list = h(ordered ? "ol" : "ul", { class: "md-list" });
      while (i < lines.length && RE_ITEM.test(lines[i])) {
        list.append(h("li", {}, renderInline(lines[i].replace(RE_ITEM, ""))));
        i += 1;
      }
      frag.append(list);
      continue;
    }
    const para = [line];
    i += 1;
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines, i)) {
      para.push(lines[i]);
      i += 1;
    }
    const p = h("p");
    para.forEach((l, k) => {
      if (k) p.append(h("br"));
      p.append(renderInline(l));
    });
    frag.append(p);
  }
  return frag;
}
