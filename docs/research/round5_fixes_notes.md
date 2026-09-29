# Round-5 fixes: source notes (29 September 2026)

These notes go with the round-5 fix entries appended to `sources_regulation.yaml` and `sources_technical.yaml`: 20 entries and 95 claims. Of the entries, 13 are `fetched` and 7 are `search_snippet_only`.

**How the sources were checked**

- **Script checks.** A validation script (kept outside the repository) checks four things:
  - Every quote is 40 words or fewer.
  - Keys are unique and do not clash with the 283 keys already in `docs/research/sources_*.yaml` or `sources_r5/*.yaml`.
  - Every quote is an exact substring, after whitespace normalisation, of either the file that was read or the recorded search-result text in `round5_search_snippets.txt`.
  - Every `fetched` URL is pinned to a commit and serves byte-identical content (HTTP 200).
- **Blocked hosts.** One WebFetch attempt was made per official URL. All of these were blocked by the egress proxy: revisor.mn.gov, ag.state.mn.us, capitol.texas.gov, leginfo.legislature.ca.gov, ftc.gov, repairfaq.org, sound-au.com, ibiblio.org, conradhoffman.com, cdp.cooley.com, opendatascience.com, einpresswire.com and worldradiohistory.com.
- **GitHub copies.** Primary texts were read from GitHub copies, each described in the entry's `container`. They are:
  - a Nov 2024 scrape of the Minnesota Revisor page;
  - a copy of the Texas codified statute;
  - a text extraction of the enrolled Texas bill;
  - the California Legislative Counsel's PUBINFO export of 9 Jul 2026;
  - the author's source files for *Lessons In Electric Circuits*;
  - a transcription of Fluke's safety sheet;
  - a 1996 archive of Goldwasser's repair FAQ.
- **Search use.** 23 web searches were used.
- **Mirror URLs.** Raw GitHub URLs will show as "MIRROR REFERENCE" in `tools/check_citations.py`. Add canonical URLs, which are given in each `container`, to `citation_overrides.yaml` if needed.

---

## 1. Minnesota Digital Fair Repair Act, Minn. Stat. § 325E.72

**Found**

- **Full statute text** (fetched, from a copy of the Revisor page scraped in Nov 2024) [`mn_325e72_digital_fair_repair`].
  - **Application clause:** "This section applies to equipment sold on or after July 1, 2021."
  - **Correction needed.** The statute says **"sold"**, not "sold or in use". "Used" appears only in the geographic scope: the duty covers equipment and parts "sold or used in Minnesota". The Attorney General's page (existing key `mn_ag_r2r`) likewise says "sold on or after July 1, 2021" and adds "Used products are included."
- **Effective date: 1 July 2024.** Search text for the Revisor's pages says: "Section 325E.72, as added by Laws 2023, chapter 57, article 4, section 11, is effective July 1, 2024" [`mn_325e72_revisor_effective_note`, snippet]. The existing `mn_ag_r2r` gives the same date.
- **Exclusions** (verbatim in the fetched text):
  - motor vehicle manufacturers, parts makers and dealers;
  - medical devices, and digital products made for use in a medical setting;
  - off-road and nonroad equipment, including farm tractors, implements and machinery, plus construction, forestry, industrial, outdoor power equipment and power tools;
  - video game consoles;
  - energy storage systems;
  - IT equipment for critical infrastructure;
  - cybersecurity-related parts and tools, except as needed for repair.
- **Other provisions:**
  - Parts, tools and documentation must be available within 60 days of first Minnesota sale.
  - The Attorney General enforces the Act (unlawful practice under § 325D.44; remedies under § 8.31).
  - Manufacturers are shielded from liability for repairs done by others.
- **Definition** (relevant to this project): "digital electronic equipment" is hardware that *depends on digital electronics to function* and for which the maker supplies tools, parts or documentation *to authorized repair providers*.

**Wording the project can use**

> Minnesota's Digital Fair Repair Act (Minn. Stat. § 325E.72), in effect since 1 July 2024, applies to digital electronic equipment sold on or after 1 July 2021. It requires manufacturers to offer documentation, parts and tools on fair and reasonable terms for equipment sold or used in Minnesota. It excludes motor vehicles, medical devices, off-road and farm equipment, video game consoles, energy storage systems and IT equipment for critical infrastructure.

**Caution (interpretation, not legal advice).** Purely analog audio gear does not meet the definition of "digital electronic equipment". The Act reaches only equipment sold on or after 1 July 2021. The Attorney General adds that used products are included; how a resale of older gear is treated was not checked.

**Not verified**

- Subdivision numbers, since the copy drops them. Do not cite "subd. N".
- The Revisor's exact NOTE wording for the effective date (snippet only).
- Whether any 2025–2026 amendment passed. Search text shows bills SF 2484/HF 2519 (motorcycles) and HF 970/SF 2030 (farm equipment) amending "Minnesota Statutes 2024, section 325E.72". Re-check the live Revisor page.
- No official text containing "sold or in use" was found.

## 2. Texas Responsible Artificial Intelligence Governance Act (TRAIGA), H.B. 149 (89th Leg., 2025)

**Found (fetched)**

- **Sources read:**
  - the codified text, Tex. Bus. & Com. Code §§ 551.001–554.103, with the history note "Added by Acts 2025, 89th Leg., R.S., Ch. 1174 (H.B. 149), Sec. 4, eff. January 1, 2026." [`tx_hb149_traiga_codified`];
  - the enrolled bill: "SECTION 10. This Act takes effect January 1, 2026" [`tx_hb149_enrolled`];
  - LegiScan's history: "Signed by the Governor" 2025-06-22; "Effective on 1/1/26" [`tx_hb149_legiscan_history`].
- **Cross-check.** Every codified quote was also found in the enrolled text.
- **Votes:** House 146–3 (23 Apr 2025); Senate 31–0 with amendments (23 May); House concurred 121–17 (30 May).
- **Private developers and deployers.** The Act applies to anyone who does business in Texas or develops or deploys AI there (§ 551.002). Its duties on private parties are only intent-based prohibitions. A person may not develop or deploy AI:
  - that "intentionally aims to incite or encourage" self-harm, harm to others or crime (§ 552.052);
  - with the sole intent to infringe constitutional rights (§ 552.055);
  - with intent to unlawfully discriminate (§ 552.056); disparate impact alone is not enough;
  - with the sole intent of producing unlawful sexual material or child sexual abuse material (§ 552.057).
- **Government-only bans:** social scoring and biometric identification (§§ 552.053–.054).
- **Disclosure.** The AI-interaction disclosure is imposed on **governmental agencies** (§ 552.051(b)). Within § 552.051 the only private-sector duty is on providers of **health-care services or treatment** (§ 552.051(f)). "Consumer" excludes anyone "acting in a commercial or employment context" (§ 551.001(2)).
- **Biometric amendment.** H.B. 149 also amended the existing biometric-identifier statute (§ 503.001), which has its own notice-and-consent rule for commercial capture. It matters to a bench tool only if the tool captures biometric identifiers.
- **Enforcement:**
  - The **Attorney General has exclusive authority**; there is **no private right of action** (§ 552.101).
  - After a complaint, the Attorney General may issue a civil investigative demand. It can ask for the system's performance metrics and known limitations (§ 552.103).
  - Written notice and a **60-day cure** period are required (§ 552.104).
  - Penalties are $10k–12k per curable violation, $80k–200k per uncurable violation and $2k–40k per day for a continuing one (§ 552.105).
  - A rebuttable presumption of reasonable care applies, with a safe harbor tied to the NIST AI RMF (§ 552.105(c), (e)).
  - No penalty action lies for an undeployed system (§ 552.105(f)).
  - State agencies can sanction their licensees only after an Attorney General finding (§ 552.106).

**Wording the project can use**

> TRAIGA (Texas H.B. 149, effective 1 January 2026) would reach a business-to-business bench diagnostic tool offered in Texas, but only through its intent-based prohibitions, such as deploying AI that intentionally aims to incite harm or crime, or with intent to unlawfully discriminate. Its AI-disclosure duty applies to government agencies and health-care providers, not to such a tool. It is enforced solely by the Texas Attorney General, with a 60-day cure period and no private right of action.

**Not verified**

- The official capitol.texas.gov pages, which were blocked. The enrolled-text copy sits next to a mismatched PDF in its repository; its text is plainly H.B. 149.
- The signing date is from LegiScan, a secondary source, and not from the official history page.

## 3. California AB 316 (2025): no "the AI did it autonomously" defense

**Found (fetched; official PUBINFO data)**

- **Bill:** AB 316 (Krell), "Artificial intelligence: defenses".
- **Signing and filing:** approved by the Governor and chaptered by the Secretary of State on **13 October 2025** as **Chapter 672, Statutes of 2025**.
- **Code section added:** **Civil Code § 1714.46**.
- **Effective date:** the history reads "Added by Stats. 2025, Ch. 672, Sec. 1. (AB 316) Effective January 1, 2026". The record is flagged non-urgency.
- **Votes:** Assembly 70–1; Senate 38–0; concurrence 78–0.
- **Operative text, § 1714.46(b):** "In an action against a defendant who developed, modified, or used artificial intelligence that is alleged to have caused a harm to the plaintiff, it shall not be a defense, and the defendant may not assert, that the artificial intelligence autonomously caused the harm to the plaintiff."
- **Preserved defenses, § 1714.46(c):** other affirmative defenses, "including evidence relevant to causation or foreseeability", and comparative-fault evidence remain available.
- **Definition, § 1714.46(a):** an engineered or machine-based system that infers from input how to generate outputs.
- **Current status:** a June 2026 digest for AB 2575 describes the rule as existing law. AB 2575 would add a new § 1714.48 and would not amend § 1714.46.

**Wording the project can use**

> California AB 316 (Stats. 2025, ch. 672, signed 13 October 2025) added Civil Code § 1714.46, effective 1 January 2026. Under it, a defendant that developed, modified or used AI may not defend a harm claim by asserting that the AI acted autonomously, although it may still contest causation and foreseeability and point to others' comparative fault.

**Not verified**

- The leginfo.legislature.ca.gov pages themselves, which were blocked. The PUBINFO copy is a third-party upload of the Legislative Counsel's export.
- AB 2575's fate after 9 July 2026.

## 4. FTC: AI performance claims need substantiation

**Found**

- **2023 staff blog post.** FTC Business Blog, M. Atleson, "Keep your AI claims in check", 27 Feb 2023: "Your performance claims would be deceptive if they lack scientific support or if they apply only to certain types of users or under certain conditions." [`ftc_keep_ai_claims_in_check_2023`, **search snippet**]. Two fetched GitHub copies quote it identically: a research note that read the Internet Archive copy, and a 3 Mar 2023 Epoch Times article.
- **2025 enforcement.** On 28 Aug 2025 the FTC finalized an order against Workado. The order requires Workado to stop advertising its AI detector's accuracy "unless it has competent and reliable evidence showing those products are as accurate as claimed" [`ftc_workado_final_order_2025`, snippet].
- The September 2024 Operation AI Comply release is already covered by round-5 keys `ftc_operation_ai_comply_2024_*`.

**Wording the project can use**

> FTC staff guidance says AI performance claims "would be deceptive if they lack scientific support" (FTC Business Blog, 2023). In August 2025 the Commission finalized an order barring an AI-detector vendor from advertising accuracy unless it has "competent and reliable evidence" that the product is as accurate as claimed.

**Not verified**

- Any ftc.gov page, which was blocked.
- The 2023 post's current status. A third party says its URL now returns 404. Search results report that the FTC removed many Khan-era blog posts in 2025; this post was not named. Present it as 2023 staff guidance, not current Commission policy, and lean on the 2025 order.

## 5. Bench practice: compare with the good channel; usual instruments

**Found**

- **Channel comparison:**
  - Elliott Sound Products (ESP): "In a stereo circuit, you can compare the level and sound from each channel at the same point in the circuit" [`esp_p164_signal_tracer`, snippet].
  - ESP: "The working amplifier gives you a pattern for each test location, and when the faulty component(s) are probed in the other amp the pattern will change" [`esp_p119_signature_analyser`, snippet].
  - Goldwasser, sci.electronics.repair FAQ, 1996 (fetched): there are "identical left and right channels to compare if an audio problem develops" [`goldwasser_cd_repair_notes_1996`]. His audio notes recommend swapping parts "between the working and dead channels" and describe how test points differ between a working and a dead channel [`goldwasser_audio_repair_notes_1996`].
- **Instruments:**
  - Goldwasser (fetched): a DMM or VOM is "necessary"; a cheap dual-trace scope is "very handy"; an audio signal source (a generator is "nice but not really essential"); an amplifier-based signal tracer; and a series light bulb as a current limiter.
  - ESP (snippets): an audio oscillator is "essential" [`esp_p22_audio_oscillator`]. A Variac lets the supply be raised slowly while the output is monitored, and a 100 W series "lamp lead" is the cheaper alternative [`esp_troubleshooting_repair_guide`].

**Wording the project can use**

> Repair references for audio equipment treat the working channel of a stereo unit as the reference, comparing signals or component signatures at the same point in each channel. They list a multimeter, an oscilloscope, an audio signal generator or signal tracer, and a Variac or series-lamp current limiter as the usual bench aids (Elliott Sound Products; Goldwasser's sci.electronics.repair notes).

**Not verified**

- Pease, *Troubleshooting Analog Circuits* (1991), and any service-manual troubleshooting section: neither could be read, so do not cite them.
- A sentence that explicitly says "compare DC voltages with the good channel". It appeared only in forum-derived search summaries, which were not recorded.
- The ESP bylines and dates. Most ESP pages are by Rod Elliott, but it was not seen here.
- The ESP page attribution for the Variac and lamp sentences, which rests on search ranking.
- The Goldwasser quotes come from the 1996 edition; the current repairfaq.org text was blocked.

## 6. Unpowered in-circuit checks

**Found (fetched)**

- **Fluke.** Fluke 110-series Safety Information (PN 5073105, Dec 2019, p. 3, via a transcription): "Disconnect power and discharge all high-voltage capacitors before you measure resistance". The same warning is transcribed for continuity, capacitance and "a diode junction" [`fluke_11x_safety_2019_discharge_warning`].
- **Kuphaldt, *Lessons In Electric Circuits* Vol. I (5th ed.):**
  - "Never try to read resistance or continuity with a multimeter on a circuit that is energized." The reason given: the meter drives its own test current, so outside voltage gives false readings or damage [`liec_v1_ch3_safe_meter_usage`].
  - "you cannot measure resistance with an ohmmeter on a 'live' circuit!" [`liec_v1_ch8_ohmmeter_design`].
- **Goldwasser (1996):** "Perform as many tests as possible with power off and the equipment unplugged", with ohmmeter checks of semiconductors as the example. Filter capacitors are discharged through a resistor and the residual charge is checked with a voltmeter.
- **ESP (snippet):** in-circuit signature testing is done with "the circuit ... powered off".

**Wording the project can use**

> Resistance, continuity and diode checks are made with the circuit unpowered and its capacitors discharged. Fluke's multimeter safety information says to "disconnect power and discharge all high-voltage capacitors" before measuring resistance, continuity, capacitance or a diode junction, and the open textbook *Lessons in Electric Circuits* warns never to read resistance or continuity on an energized circuit.

**Not verified**

- The Fluke PDF itself. The transcriber split one warning sentence into four records, one per test mode, with ellipses; the full sentence was not seen.
- The ibiblio and All About Circuits pages of the textbook (blocked; the textbook's wording was read from the author's source files).
- The book's own "de-energized components!" sentence is not quoted because of markup in the source.
