# Differential: regulation, safety, ethics and governance notes

*Status as of 28 September 2026. Source keys refer to `sources_regulation.yaml`.*

**Scope.** Differential is an LLM agent paired with a Bayesian diagnosis engine. It recommends measurements to a qualified bench technician working on analog audio gear, including tube equipment with B+ rails around 250 V DC. Mains-side work is out of scope. This is a student analysis, not legal advice.

**How far to trust the sources.** Most official hosts were blocked from the research sandbox.

- **`fetched`:** verbatim text we opened ourselves. Some of it came from GitHub reproductions of official text: the AI Act and GDPR articles, the OSHA sections, and Gender Shades from PMLR's own repository.
- **`search_snippet_only`:** wording taken from search-result text for the official page.

Re-check both kinds against the official text before final submission. Anything we could not verify is listed under "Gaps" at the end.

---

## A. EU AI Act (Regulation (EU) 2024/1689) and the Digital Omnibus

### Timeline as of September 2026

| Date | What applies or happens | Keys |
|---|---|---|
| 12 Jul 2024 | Published in the OJ (OJ L, 2024/1689) | [eu_ai_act_text_mirror] |
| 1 Aug 2024 | Entry into force | [eu_ai_act] |
| 2 Feb 2025 | Chapters I–II: AI literacy (Art. 4) and prohibited practices (Art. 5) | [eu_ai_act_text_mirror], [ec_ai_literacy_qa] |
| 2 Aug 2025 | GPAI obligations (Ch. V), governance, penalties and notified bodies | [eu_ai_act_text_mirror], [eurlex_summary_ai_act] |
| 19 Nov 2025 | Commission proposes the Digital Omnibus on AI | [ec_ai_omnibus_in_force] |
| 7 May 2026 | Provisional agreement between Council and Parliament | [council_pr_2026_05_07] |
| Jun 2026 | Parliament approves; Council adopts on 29 Jun | [ep_pr_2026_06_ai_omnibus], [council_pr_2026_06_29] |
| 8 / 24 / 27 Jul 2026 | Regulation (EU) 2026/1744 signed, published and in force | [eu_ai_omnibus_2026_1744], [ec_ai_omnibus_in_force] |
| 2 Aug 2026 | General application: enforcement starts, the Art. 50 transparency duties apply, and the AI Office can enforce against new GPAI models | [ec_ip_26_1714], [ec_ip_25_1787_gpai_code] |
| 2 Dec 2026 | Art. 50(2) marking grace period ends for generative systems on the market before 2 Aug 2026 | [council_pr_2026_05_07] |
| 2 Aug 2027 | Deadline for GPAI models placed on the market before 2 Aug 2025 | [ec_ip_25_1787_gpai_code] |
| **2 Dec 2027** | High-risk rules for **Annex III** systems (originally 2 Aug 2026) | [eu_ai_omnibus_2026_1744], [council_pr_2026_06_29] |
| **2 Aug 2028** | High-risk rules for **Annex I** product-embedded systems (originally 2 Aug 2027) | same |

**Omnibus status: adopted and in force.** It sets a fixed timeline for the delayed high-risk rules [council_pr_2026_06_29]. Its other changes:

- **AI literacy.** Art. 4 was softened from "ensure, to their best extent, a sufficient level" [eu_ai_act_text_mirror] to "take measures to support the development" of AI literacy, and the Commission and Member States must support SMEs [eu_ai_act_consolidated_2026].
- **New prohibition.** AI generation of non-consensual intimate imagery and CSAM is now banned [council_pr_2026_05_07].
- **Annex I Section B.** Products covered by Section B legislation are now subject only to Art. 6(1), Art. 60a and Arts. 102–112 [eu_ai_act_consolidated_2026].
- **Machinery (unverified).** Commentators report that the Machinery Regulation moved to Section B; this is not confirmed against the OJ text.

The Commission's Art. 6 classification guidelines are still in draft, with finalisation due by the end of 2026 [ec_draft_highrisk_guidelines_2026].

### Risk tier for Differential

1. **Art. 5 prohibitions:** none apply.
2. **Art. 6(1), Annex I products.** This route requires both conditions [eu_ai_act_text_mirror]:
   - the system is a safety component of, or itself, an Annex I product; and
   - that product needs third-party assessment.

   Neither holds. Amplifiers are low-voltage equipment (50–1000 V AC / 75–1500 V DC) [eu_lvd_2014_35]. The Low Voltage Directive is not among Annex I's 20 listed acts, and the EMC Directive appears only inside another act's title [eu_ai_act_text_mirror]. The Radio Equipment Directive *is* listed (item 6), so wireless audio products come closer. Even so, Differential is a separate bench tool, not a safety component of the device under repair. A snippet also suggests that assessment required only because of spectrum or EMI does not satisfy Art. 6(1)(b); this needs verifying [eu_ai_act_consolidated_2026]. **Not high-risk.**
3. **Art. 6(2), Annex III.** No listed area covers diagnostics [eu_ai_act_text_mirror]. **Caveat:** point 4(b) covers AI that monitors or evaluates workers' performance. Logs should therefore support fault analytics, not scoring of individual technicians.
4. **Art. 50.** Since 2 August 2026, systems that interact with people must disclose that they are AI "unless this is obvious" [eu_ai_act_text_mirror], [ec_ip_26_1714]; a visible "AI assistant" label suffices. It is an open question whether Art. 50(2) machine-readable marking of synthetic text applies to measurement advice, given the assistive-function exception. Track this through the transparency Code of Practice, which has 180+ signatories [ec_ip_26_1714].
5. **Art. 4.** Providers and deployers (the repair shop) must take AI-literacy measures [eu_ai_act_consolidated_2026]. Onboarding material and "why this measurement?" explanations can serve as evidence.
6. **GPAI duties** fall on the upstream model vendor.

**Net: limited-risk (transparency) tier, plus the AI-literacy duty.**

---

## B. NIST AI RMF and US policy

**The framework.** The AI RMF 1.0 (26 January 2023) is voluntary [nist_ai_rmf_page], [nist_ai_rmf_playbook]. Its core has four functions [nist_ai_rmf_1_0]:

- **GOVERN** (cross-cutting);
- **MAP** (context);
- **MEASURE** (assess risk);
- **MANAGE** (treat risk).

**2024–2026 NIST developments.**
- **Generative AI Profile.** NIST AI 600-1 (26 July 2024) covers 12 risks and just over 200 actions [nist_ai_600_1].
- **Revision.** NIST is revising RMF 1.0 under the AI Action Plan, removing references to misinformation, DEI and climate change. No new version had been found by September 2026 [nist_ai_rmf_page], [nist_ai_update_2026_03].
- **Critical-infrastructure profile.** Concept note issued 7 April 2026 [nist_ai_rmf_page].
- **Cyber AI Profile.** NIST IR 8596 preliminary draft issued December 2025 [nist_ir_8596_cyber_ai_profile].
- **Agent security.** NIST's CAISI ran an agent-security RFI and launched an AI Agent Standards Initiative [fr_caisi_rfi_ai_agents_2026], [nist_ai_agent_standards_2026].

**Mapping for Differential.**
- **Govern:** roles and a written safety policy (§E).
- **Map:** a qualified technician working on de-energised versus live tube circuits.
- **Measure:** disaggregated accuracy, calibration and unsafe-suggestion rate (§G).
- **Manage:** confirmation gates, incident logs and rollback.

**Federal policy** leans deregulatory, with a push toward preempting state law:

- **EO 14179** (Jan 2025) [eo_14179].
- **AI Action Plan** (Jul 2025, 90+ actions) [us_ai_action_plan_2025].
- **EO 14365** (11 Dec 2025) [eo_14365]:
  - created a DOJ AI Litigation Task Force against state AI laws;
  - ordered a Commerce review of "onerous" state laws;
  - requested an FTC Section 5 statement.
- **Legislative framework** (20 Mar 2026) [wh_ai_legislative_framework_2026].
- **FTC proposed policy statement** (7 Jul 2026): covertly "steering" outputs may be deceptive even when done to comply with state law [ftc_ai_accuracy_policy_2026].
- **EO 14409** (Jun 2026) on AI-era cyber defence of government systems [eo_14409].

H.R. 5388 proposes a moratorium preempting state AI laws [us_hr_5388]. We found no enacted federal preemption statute, though our search was limited.

**Colorado.** SB 24-205 was delayed to 30 June 2026 [co_sb25b_004]. It was then repealed and re-enacted by SB26-189 (signed 14 May 2026) as a narrower automated decision-making technology regime for "consequential decisions", mostly effective 1 January 2027 [co_sb26_189]. Advice on bench measurements is unlikely to qualify, but check the definitions.

---

## C. Right to repair

**EU.** Directive (EU) 2024/1799 has applied since 31 July 2026 [ec_r2r_news_2026_07_31]:

- The duty to repair, the ban on techniques that impede repair, and "reasonable price" parts and tools cover only goods listed in **Annex II**, the products with EU reparability rules [eu_r2r_directive_2024_1799].
- Repair adds one year of legal guarantee [ec_r2r_news_2026_07_31].

Annex II covers ecodesign groups such as washing machines, dishwashers and electronic displays [ec_r2r_qa_2024]. It grows by delegated act, most recently adding local space heaters in January 2026 [eu_deleg_dir_2026_74]. **Audio amplifiers are not covered, and no schematic mandate follows.**

**US digital-electronics laws**

| State (citation) | In force | Cut-off / threshold | Audio electronics? | Documentation / schematics? | Keys |
|---|---|---|---|---|---|
| New York, Gen. Bus. Law § 399-nn | 28 Dec 2023 | First sold ≥ 1 Jul 2023; digital electronics | Yes if digital (AG: "home entertainment systems") | Yes: "schematic diagram"; no trade secrets | [ny_gbl_399nn], [ny_ag_repair_2024] |
| Minnesota, Minn. Stat. § 325E.72 | 1 Jul 2024 | Sold ≥ 1 Jul 2021 | Likely if digital (not expressly verified) | Yes: docs, parts, tools, firmware updates | [mn_stat_325e72], [mn_ag_r2r] |
| California, Pub. Res. Code § 42488 et seq. | 1 Jul 2024 | ≥ 1 Jul 2021; $50–99.99 → 3 yrs; ≥ $100 → 7 yrs | Yes ("electronic or appliance product") | Yes: includes "schematic" | [ca_prc_42488], [ca_bhgs_r2r_advisory_2024] |
| Oregon, SB 1596 (2024 ch. 69) | 1 Jan 2025 | Non-phones pre-1 Jul 2015 excluded; parts-pairing ban | Yes if digital | Yes: parity with authorised providers | [or_sb1596_2024] |
| Colorado, HB24-1121 | 1 Jan 2026 | ≥ 1 Jul 2015 (phones ≥ 1 Jul 2021); digital | Yes if digital | Yes, free of charge | [co_hb24_1121] |
| Washington, ESHB 1483 (2025 ch. 353) | 1 Jan 2026 | ≥ 1 Jul 2021 | Yes if digital | Yes | [wa_eshb1483_2025] |
| Texas, HB 2963 (Bus. & Com. Code ch. 121) | **1 Sep 2026** | Wholesale ≥ $50; within 1 year of first sale; AG enforces | Yes if digital | Yes | [tx_hb2963_2025] |

**What this means for Differential:**
- **Scope.** Every law requires dependence on *digital* electronics and a post-cut-off sale date. **Vintage all-analog tube amplifiers are generally outside all of them.** Modern DSP, streaming or microcontroller-based gear usually falls inside.
- **Parity only.** Access is limited to what the manufacturer already gives its authorised repairers.
- **Legacy schematics** must come from elsewhere. Their licensing is unverified, so Differential should record provenance for every retrieved document.

**Federal.**
- **FTC report.** *Nixing the Fix* (2021) found "scant evidence" for manufacturers' repair restrictions [ftc_nixing_the_fix_2021], followed by an enforcement policy statement [ftc_repair_policy_statement_2021].
- **Warranty letters.** In 2024 FTC staff warned companies about "void if removed" stickers [ftc_warranty_letters_2024].
- **Deere settlement.** The FTC and states' July 2026 settlement gives independent repairers 10 years of dealer-equivalent diagnostic software and manuals [ftc_deere_settlement_2026].
- **Copyright.** The Section 1201 exemptions allow circumventing consumer-device firmware locks for repair [cfr_37_201_40], [usco_1201_ninth_2024]; they do not give access to documents. The 2027 cycle is open, with renewal comments due 28 September 2026 [usco_1201_tenth_2027].

---

## D. Liability and accountability

**EU.** The Product Liability Directive (EU) 2024/2853 [eu_pld_2024_2853]:

- counts software as a "product";
- must be transposed by 9 December 2026;
- applies to products placed on the market after that date;
- excludes damage to property used exclusively for professional purposes.

A commercial Differential in the EU would therefore be a product, and injury caused by a defect, such as a shock, could attract strict liability. Whether erroneous *advice* counts as a defect is unsettled.

**Unverified.** We could not verify the withdrawal of the AI Liability Directive proposal (see Gaps).

**US.** Two bills have been introduced; we found no enactment.
- The **AI LEAD Act (S. 2937)** would treat AI systems as products [us_ai_lead_act_s2937].
- The **RISE Act (S. 2081)** would shield developers when a *learned professional* uses the tool, if they publish a model card and specification. Professionals would keep the duty to "verify the system's outputs" [us_rise_act_s2081].

Differential fits this model: the technician decides and the tool explains itself. Publish a model card.

**Professional codes.** The IEEE and NSPE public-safety canons are central to our argument, but they are unverified (see Gaps). Do not quote them yet.

---

## E. Electrical safety

**OSHA's verified benchmarks:**
- **Default rule:** de-energise exposed live parts before work [osha_1910_333].
- **50 V threshold.**
  - Parts under 50 V to ground are exempt from de-energising if there is no added burn or arc risk [osha_1910_333].
  - Parts at 50 V or more must be guarded [osha_1910_303].
- **Stored energy:** "Capacitors shall be discharged and high capacitance elements shall be short-circuited and grounded", and capacitors being handled are "treated as energized" [osha_1910_333].
- **Verification:** a qualified person must verify the dead state with test equipment [osha_1910_333].
- **Testing:** only qualified persons may test, and instruments must be rated for the circuit [osha_1910_334].
- **Qualification** is equipment-specific [osha_1910_331_399].

**Which rules reach bench work.** 1910.269 covers utility work and excludes work covered by Subpart S [osha_1910_269]. Subpart S itself is framed around premises wiring [osha_1910_331_399]. We therefore use these rules as the authoritative benchmark, not as a claim about OSHA jurisdiction over bench repair.

**Design rules for Differential.** B+ at around 250 V is far above 50 V.
1. Treat any node that can exceed 50 V as hazardous.
2. Prefer de-energised measurements when they can discriminate between hypotheses.
3. Require "discharge, then verify with a rated meter" before any hands-in step.
4. Allow live measurements only after the technician confirms qualification and suitable meter ratings.
5. Refuse mains-side procedures.

**Unverified:** NFPA 70E, IEC 61010-1 measurement categories (possibly in IEC 61010-2-030) and IEC 62368-1 ES1/ES2/ES3 (see Gaps).

---

## F. Privacy

**GDPR:**
- **Art. 5(1)(c)** limits personal data to "what is necessary" [gdpr].
- **Art. 25(1)** requires protection by design, for example pseudonymisation [gdpr].
- **Art. 25(2)** requires protection by default: only the data necessary for each purpose may be processed. This limits the amount collected, the extent of processing, the storage period and who can access it [gdpr].

**For a shop running Differential:**
- keep customer identity separate from equipment and fault records, keyed by a pseudonymous job ID;
- never send customer PII to the LLM;
- set retention limits;
- de-identify the fault statistics used to update the Bayesian priors.

CCPA/CPRA thresholds are unverified.

---

## G. Bias auditing

*Gender Shades* found error rates of up to 34.7% for darker-skinned females against at most 0.8% for lighter-skinned males. It got there by disaggregating accuracy into **intersectional subgroups** on a benchmark rebuilt for balance. The authors argue that this analysis should guide dataset and model design [buolamwini_gebru_2018].

**Transfer to Differential:**
- **Axes.** Stratify evaluation cases by:
  - circuit technology (tube or solid-state);
  - era and manufacturer;
  - fault class (open, short, drift, intermittent);
  - documentation availability;
  - technician experience.
- **Metrics per cell.** Top-k localisation accuracy, measurements-to-diagnosis, posterior calibration, and unsafe-suggestion rate.
- **Balance.** Build a balanced test set, so that tube and undocumented gear are not under-sampled.

NISTIR 8280 is unverified.

---

## H. Security: prompt injection

**The threat.** Differential reads untrusted text: scanned manuals, forum posts and customer notes. That is the route for **indirect prompt injection**, in which adversaries plant prompts "into data likely to be retrieved" [greshake_2023], with effects "as powerful as arbitrary code execution" [greshake_llm_security_repo].
- NIST defines it as injection "executed through resource control" [nist_csrc_glossary_prompt_injection].
- NIST AI 100-2 E2025 treats it in a dedicated section [nist_ai_100_2_e2025].
- CAISI frames agent hijacking as a form of it [nist_caisi_agent_hijacking_2025].

**No complete fix exists.**
- OWASP 2025 says RAG and fine-tuning "do not fully mitigate" injection [owasp_llm_top10_2025].
- The UK NCSC says it may never be totally mitigated [ncsc_prompt_injection_2025].
- The **OWASP Top 10 for LLM Applications 2026** (published 4 August 2026, superseding 2025) keeps injection at LLM01, raises Excessive Agency to third, and requires defence in depth because "no single control is sufficient" [owasp_llm_top10_2026].

**Controls** [owasp_llm_top10_2026], [owasp_llm_top10_2025]:
1. Keep credentials and any instrument or relay control in application code, with least privilege.
2. Require technician confirmation for any state-changing action.
3. Apply the **Rule of Two**: untrusted input plus sensitive data plus state change means approval for every action.
4. Label the provenance of retrieved content.
5. Validate every LLM suggestion against the Bayesian engine and hard safety rules.

CaMeL-style capability separation is a useful pattern, but its authors call their artifact possibly not fully secure [debenedetti_camel_2025]. OWASP's LLM07 describes the non-adversarial failure: wrong output that is "trusted and acted upon" [owasp_llm_top10_2026].

---

## I. Levels of autonomy: an analogy to J3016

SAE J3016 (April 2021) defines Levels 0–5 by who performs the task and who is the fallback [kulicki_trypuz_j3016_ontology]:

- **L2:** the human supervises.
- **L3:** the system drives, but a fallback-ready user must respond to requests.
- **L4:** the system handles its own fallback, but only inside its operational design domain (ODD).
- **L5:** the same as L4 but unconditional.

These definitions were verified through a CC-licensed ontology reproducing J3016 §§5.1–5.6. SAE's page, and any newer revision, are unverified.

**Proposed levels of diagnostic autonomy:**
- **D0:** manual diagnosis.
- **D1:** a single aid, such as computing expected voltages.
- **D2:** Differential ranks hypotheses and recommends the next measurement, while the technician performs and judges everything. **This is our target.**
- **D3:** automated sequencing within a narrow ODD, such as de-energised checks, with the technician as fallback.
- **D4–D5:** out of scope for high-voltage gear.

The D3 ODD should exclude live measurements above 50 V (§E). The analogy is weaker than in driving because the human, not the tool, touches the hazard.

---

## J. Ethical frameworks and work

**Not yet verified:** the three SEP entries (consequentialism, deontology, virtue ethics), Acemoglu & Restrepo, and Brynjolfsson, Li & Raymond (*QJE* 2025). They are uncited here.

**Framing to fill once sourced:**
- **Consequences:** shock risk, repair success, customer cost.
- **Duties:** honest AI disclosure (compare Art. 50), and technician authority and consent.
- **Virtues:** the tool should build craft judgement, not erode it.
- **Labour:** the evidence needed is on augmenting versus replacing workers, particularly whether assistance helps less-experienced workers most.

---

## Five most recent regulatory actions relevant to AI-assisted repair

1. **1 Sep 2026:** Texas HB 2963 takes effect [tx_hb2963_2025].
2. **2 Aug 2026:** AI Act enforcement starts and Art. 50 transparency applies [ec_ip_26_1714].
3. **31 Jul 2026:** the EU Repair Directive applies [ec_r2r_news_2026_07_31].
4. **27 Jul 2026:** Regulation (EU) 2026/1744 enters into force [eu_ai_omnibus_2026_1744].
5. **8 Jul 2026:** the FTC and states settle with Deere [ftc_deere_settlement_2026]. The FTC also proposed its AI-accuracy policy statement on 7 July [ftc_ai_accuracy_policy_2026].

---

## Gaps and verification to-do

These items could not be verified: official hosts were blocked and the web-search budget ran out. They are not in the YAML.

1. **AI Liability Directive:** withdrawal of the proposal (COM(2022) 496), with date and OJ notice.
2. **Ethics codes:** IEEE Code of Ethics (Policies §7.8); NSPE Code, Canon 1.
3. **Electrical-safety standards:**
   - NFPA 70E: current edition, 50 V and energized-work provisions, capacitor provisions;
   - IEC 61010-1 / 61010-2-030: measurement categories;
   - IEC 62368-1: ES classes.
4. **CCPA/CPRA:** Cal. Civ. Code § 1798.100 et seq., current thresholds, CPPA regulations.
5. **NISTIR 8280** (2019).
6. **SAE J3016:** SAE's own page and latest revision.
7. **Ethics and labour sources:** the SEP entries; Acemoglu & Restrepo; Brynjolfsson, Li & Raymond.
8. **Omnibus details to confirm in the OJ text:**
   - the machinery move;
   - the Art. 6(1)(b) spectrum/EMI clarification;
   - when the new prohibition applies;
   - the exact date of Parliament's plenary vote.
9. **Snippet-only quotes:** re-read every `search_snippet_only` quote on its official page.
