// Shared Typst styles for Differential milestone documents.
#let ink = rgb("#1b2430")
#let muted = rgb("#5b6675")
#let accent = rgb("#0b6e69")
#let accent-soft = rgb("#e6f2f1")
#let rule-col = rgb("#cfd6dd")

#let setup(title: "", short: "", body) = {
  set document(title: title)
  set page(
    paper: "us-letter",
    margin: (x: 0.85in, top: 0.8in, bottom: 0.8in),
    numbering: "1",
    number-align: center,
    header: context {
      if counter(page).get().first() > 1 [
        #set text(font: "Inter", size: 7.5pt, fill: muted)
        #short #h(1fr) Differential
        #v(-6pt)
        #line(length: 100%, stroke: 0.4pt + rule-col)
      ]
    },
    footer: context [
      #set text(font: "Inter", size: 7.5pt, fill: muted)
      #h(1fr) #counter(page).display("1") #h(1fr)
    ],
  )
  set text(font: "Bitstream Charter", size: 10pt, fill: ink, lang: "en")
  set par(justify: true, leading: 0.58em, spacing: 0.8em)
  show heading: set text(font: "Inter", fill: ink)
  show heading.where(level: 1): it => {
    v(0.7em)
    text(size: 12.5pt, weight: "bold", it.body)
    v(0.25em)
  }
  show heading.where(level: 2): it => {
    v(0.45em)
    text(size: 10.5pt, weight: "semibold", it.body)
    v(0.1em)
  }
  show heading.where(level: 3): it => {
    v(0.3em)
    text(size: 10pt, weight: "semibold", style: "italic", it.body)
  }
  show figure.caption: it => {
    set text(size: 8.6pt)
    set par(justify: true)
    block(width: 100%, [#text(font: "Inter", weight: "semibold", fill: accent)[#it.supplement #context it.counter.display(it.numbering).] #it.body])
  }
  set figure(gap: 0.5em)
  // Table captions above the table (IEEE style), so a caption never lands on another page.
  show figure.where(kind: table): set figure.caption(position: top)
  show figure: set block(breakable: false)
  set table(stroke: (x, y) => (
    top: if y == 0 { 0.8pt + ink } else if y == 1 { 0.5pt + ink } else { 0pt },
    bottom: 0.5pt + rule-col,
  ), inset: (x: 4pt, y: 2pt), align: left + top)
  show table: set text(size: 8.4pt)
  show table: set par(justify: false, leading: 0.5em)
  show table.cell.where(y: 0): set text(font: "Inter", weight: "semibold", size: 8pt)
  show link: set text(fill: accent)
  set list(indent: 0.6em, spacing: 0.55em)
  set enum(indent: 0.6em, spacing: 0.55em)
  show raw: set text(font: "DejaVu Sans Mono", size: 8.2pt)
  body
}

#let title-block(title: "", subtitle: "", meta: ()) = {
  block(width: 100%, inset: (bottom: 6pt))[
    #text(font: "Inter", size: 8pt, weight: "semibold", fill: accent, tracking: 0.08em)[#upper(subtitle)]
    #v(-2pt)
    #text(font: "Inter", size: 17pt, weight: "bold")[#title]
    #v(-4pt)
    #text(font: "Inter", size: 8pt, fill: muted)[#meta.join("  ·  ")]
  ]
  line(length: 100%, stroke: 0.8pt + ink)
}

// Signed part header. The PART markers are read by tools/check_balance.py.
#let part(n, title, lead) = {
  v(0.6em)
  block(width: 100%, fill: accent-soft, inset: (x: 8pt, y: 6pt), radius: 2pt)[
    #text(font: "Inter", size: 11.5pt, weight: "bold")[Part #n — #title]
    #h(1fr)
    #text(font: "Inter", size: 8pt, fill: muted)[Section lead: #lead]
  ]
  v(0.2em)
}

#let decision(title, body) = block(
  width: 100%,
  stroke: (left: 2pt + accent),
  inset: (left: 8pt, y: 4pt, right: 4pt),
  breakable: true,
)[
  #block(sticky: true, below: 0.5em)[#text(font: "Inter", size: 8.4pt, weight: "semibold", fill: accent)[DESIGN DECISION · #title]]
  #set text(size: 9.4pt)
  #body
]

#let note(body) = block(width: 100%, fill: rgb("#f5f7f9"), inset: 6pt, radius: 2pt)[
  #set text(size: 9pt)
  #body
]

#let ref-entry(n, body) = {
  set text(size: 7.9pt)
  set par(justify: false, hanging-indent: 1.9em, leading: 0.45em, spacing: 0.4em)
  [\[#n\] #h(0.2em) #body]
  parbreak()
}
