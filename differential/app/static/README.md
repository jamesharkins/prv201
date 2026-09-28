# Differential web UI

A no-build single-page front end for the FastAPI app in `differential/app/server.py`.
Plain ES modules, one stylesheet, no framework, no bundler and no external requests:
fonts come from the system (Inter when installed locally, then `system-ui`), icons are
inline SVG, and the favicon is a data URI. The page works fully offline.

Run the server (`make demo` or `python -m differential.app.server`) and open
http://127.0.0.1:8000.

## Layout

```
┌ header: Differential · circuit selector · mode badge · New unit · Ticket · Reveal (demo) · theme ┐
├──────────────────────────────────────────────┬─────────────────────────────────────────┤
│ Schematic panel (left, large)                │ Right column (scrolls on its own)       │
│  light or dark SVG of the circuit            │  a) safety banner (when the pending     │
│  test-point hotspots with hazard rings       │     step is high voltage or locked)     │
│  reading labels, pulsing "next" point        │  b) next measurement card + "Why this?" │
│  popover per test point, pan/zoom, legend    │  c) belief: bars, no-single-fault row,  │
│                                              │     history chart, effort meter         │
│                                              │  d) conversation + meter photo          │
│                                              │  e) readings table                      │
└──────────────────────────────────────────────┴─────────────────────────────────────────┘
```

Without a session the right column shows the start screen (what the demo does and a
"Start with a simulated unit" button) and the schematic previews the selected circuit.
Below 900 px the two columns stack.

## Files

| File | What it does |
|---|---|
| `index.html` | Page skeleton; a tiny inline script applies the theme before first paint. |
| `styles.css` | Colour tokens for both themes as custom properties, layout, components. |
| `app.js` | Entry module: header, start screen, session state, wiring of every panel to the API. |
| `modules/api.js` | `fetch` wrapper for every endpoint; turns FastAPI errors into readable messages. |
| `modules/schematic.js` | Schematic panel: SVG, hotspots from the test-point map, labels, popover, pan/zoom. |
| `modules/panels.js` | Safety banner (with the discharge form), next-measurement card, readings table. |
| `modules/belief.js` | Belief bars with animated transitions, groups, history chart, effort meter. |
| `modules/chat.js` | Transcript, composer, quick prompts, meter-photo upload and confirmation. |
| `modules/ticket.js` | Ticket dialog: verdict, belief at close, evidence, sign-off, `.md`/`.json` downloads. |
| `modules/forms.js` | Reading, lift-result and discharge forms (unit conversion, validation). |
| `modules/markdown.js` | Tiny Markdown renderer that builds DOM nodes (HTML in the source stays text). |
| `modules/format.js` | Units, percentages, part descriptions, the stage-to-colour mapping. |
| `modules/theme.js` | Light/dark theme: OS preference by default, choice kept in `localStorage`. |
| `modules/dom.js` | Element helpers, inline icons, toasts, screen-reader announcements. |

## Data flow

Every action posts to the API and re-renders from the returned `state` (see `_state` in
`server.py`): `pending` drives the banner, the next card and the pulsing test point;
`top_hypotheses`, `belief` and `history` drive the belief panel; `readings` drive the
labels on the schematic and the table; `transcript` drives the conversation. Circuit
details (test points, hazard levels, parts, schematic URLs and the test-point map in SVG
viewBox units) come from `GET /api/circuits/{id}`. The session id is kept in
`sessionStorage`, so a reload reopens the same session while the server runs.

Readings typed in the UI are converted to the engine's units before they are sent (mV to
V, dB to V/V). Nothing from a meter photo is recorded until the technician picks the
measurement and confirms the value. Rejected readings come back from the agent as a reply
("I couldn't record that: ...") and are shown next to the form.

## Visual encoding

- Hazard rings on test points: high voltage in red with a lightning badge, high voltage
  possible under a fault in amber with a dashed ring and badge, low voltage in teal. The
  legend names each one; the recommended point gets a pulsing double ring and a "Next" tag
  (static when the OS asks for reduced motion).
- Belief bars take the colour of the suspect part's circuit stage (fixed order from
  `eval/figstyle.py`: LV supply, HV supply, triode, tone, op-amp, line driver); every bar
  also names the part and the stage in text. Faults that no measurement can tell apart are
  tagged with a shared group letter. The probability that no single fault fits is a
  separate hatched row.
- Text uses ink colours that meet WCAG AA contrast in both themes. Bar colours that fall
  below 3:1 on the light surface (yellow, aqua, magenta) always sit next to a text label
  and a value.

## Accessibility

All controls are native buttons, inputs, `<details>` and `<dialog>`; focus is always
visible; icon-only buttons have `aria-label`s; test points are buttons with a spoken
hazard level; the popover and the ticket dialog return focus when closed. The schematic
pans with the arrow keys and zooms with `+`, `-` and `0`. The transcript is a polite live
region, and recorded readings and safety banners are announced. The history chart has a
screen-reader table twin.

## Demo hooks

`?circuit=<id>` preselects a circuit. `?fault=<fault id>&seed=<n>` fix the hidden fault
and the unit for a scripted demo (the server's `NewSession` accepts both); they are used by
`tools/screenshots.py`, which drives a full session in Playwright and writes the
screenshots in `docs/media/screenshots/` and `docs/media/demo.gif`.
