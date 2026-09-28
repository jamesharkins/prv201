# Technical notes: Differential evidence base

Compiled 2026-09-28. Companion to `sources_technical.yaml` (75 sources, 191 quoted claims).
Every number below carries its source key in square brackets. Values marked *derived* are my own arithmetic on sourced numbers, not quotations.

## 0. How the values were checked, and what that means for citing them

- **Network constraints.** The sandbox's egress allowlist blocked the primary hosts for most of this topic: manufacturers (onsemi, ST, Vishay, Yageo, WIMA, Nichicon, Fluke, Rigol, Siglent), publishers and indexes (doi.org, IEEE Xplore, arXiv, ACM, JSTOR, Project Euclid), normankoren.com, frank.pocnet.net, alldatasheet and Wikipedia. The session-wide WebSearch budget (200 calls, shared with other agents) was exhausted after this agent's first 8 queries. Reachable hosts were GitHub (raw/git), SourceForge, PyPI and platform.claude.com.
- **Mirrors.** Most primary documents were therefore read from GitHub copies. The `url` of each such entry is pinned to a commit SHA, and the entry's `container` names the repository. Where the original PDF could be downloaded (onsemi 2N3903/D and 2N3906/D, ST BD139, Philips 1N4728A, ROHM 1N4148, Good-Ark, MOSPEC, Philips ECC83), its identity was checked from the document itself: revision line, logo, or dates.
- **Quote checking.** A script checked every text quote against the downloaded copy after whitespace normalisation: 191 claims, 0 mismatches. It could not check two kinds of quote. The first kind was read by eye from rendered pages of scanned PDFs: the ECC83 tables, the TIP31 table, the ROHM electrical table and the ± signs of the Good-Ark tolerance line. The second kind is 2 search-engine snippets for the two normankoren.com pages, marked `search_snippet_only`.
- **Bibliographic records.** IEEE DOIs, pages and abstracts come from the CIRDC dataset `[cirdc_ieee_metadata_dataset]`, a GitHub mirror of IEEE Xplore metadata up to April 2025. Non-IEEE DOIs come from reference lists and BibTeX files in maintained open-source repositories: scikit-learn, MAPIE, LightGBM, linfa, elki and others. Each was downloaded. These confirm the bibliographic details only. None of the ML or statistics papers themselves was opened, except the Guo et al. abstract page.
- **Corrections to commonly remembered DOIs.** Both of these were found during checking; use the values given here.
  - Bandler & Salama (1985) is **10.1109/PROC.1985.13281**.
  - Pattipati & Alexandridis (1990) is **10.1109/21.105086**, *IEEE SMC* 20(4):872-887.

---

## A. Koren triode model and the 12AX7

### A.1 Model equations: verbatim SPICE listing `[koren_tube_lib_1996_mirror]`

This is the 12AX7 "NEW MODEL" subcircuit from Koren's library file (Glass Audio Vol. 8, No. 5, 1996), as mirrored at https://raw.githubusercontent.com/ajmwagar/pedalkernel/0278b397c861b5ebef2e8e38d15ab281b8e669dc/pedalkernel/models/tubemods_tmp/Tube.lib:

```spice
.SUBCKT 12AX7 1 2 3  ; P G C;  NEW MODEL
+ PARAMS: MU=100 EX=1.4 KG1=1060 KP=600 KVB=300 RGI=2000
+ CCG=2.3P  CGP=2.4P CCP=.9P  ; ADD .7PF TO ADJACENT PINS; .5 TO OTHERS.
E1 7 0 VALUE=
+{V(1,3)/KP*LOG(1+EXP(KP*(1/MU+V(2,3)/SQRT(KVB+V(1,3)*V(1,3)))))}
RE1 7 0 1G
G1 1 3 VALUE={(PWR(V(7),EX)+PWRS(V(7),EX))/KG1}
RCP 1 3 1G    ; TO AVOID FLOATING NODES IN MU-FOLLOWER
C1 2 3 {CCG}  ; CATHODE-GRID
C2 2 1 {CGP}  ; GRID=PLATE
C3 1 3 {CCP}  ; CATHODE-PLATE
D3 5 3 DX     ; FOR GRID CURRENT
R1 2 5 {RGI}  ; FOR GRID CURRENT
.MODEL DX D(IS=1N RS=1 CJO=10PF TT=1N)
.ENDS
```

In mathematical form, with node 1 = plate P, 2 = grid G, 3 = cathode K and all voltages referred to the cathode:

- **E1 = (V_PK / KP) · ln[ 1 + exp( KP · ( 1/MU + V_GK / sqrt(KVB + V_PK²) ) ) ]**. SPICE `LOG` is the natural logarithm; ngspice's `log` is also base e `[ngspice_manual_v47]`.
- **I_P = (PWR(E1,EX) + PWRS(E1,EX)) / KG1**. With PSpice semantics, PWR = |x|^y and PWRS = sgn(x)·|x|^y; these are the definitions ngspice applies in PSPICE-compatibility mode `[ngspice_inpcompat_source]`. So I_P = 2·E1^EX / KG1 for E1 > 0, and I_P = 0 for E1 ≤ 0 (*derived*).
  - This matches the article form I_P = (E1^EX / KG1)·(1 + sgn(E1)) seen in a search snippet of Koren's article `[koren_article_web_part1]` (search snippet only).
- **Grid current:** diode `DX` (IS = 1 nA, RS = 1 Ω, CJO = 10 pF, TT = 1 ns) in series with RGI = 2 kΩ, from grid to cathode.
- **Capacitances:** CCG, CGP and CCP are lumped capacitors. RCP = 1 GΩ from plate to cathode avoids floating nodes in a mu-follower.

### A.2 Published 12AX7 parameter sets

| Model | MU | EX | KG1 | KP | KVB | VCT | RGI (Ω) | CCG | CGP | CCP | Source |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Koren 12AX7 "NEW MODEL" (1996) | 100 | 1.4 | 1060 | 600 | 300 | none in the original | 2000 | 2.3 pF | 2.4 pF | 0.9 pF | `[koren_tube_lib_1996_mirror]` |
| Koren 12AX7 "OLD MODEL" (superseded) | 93 | 1.5 | 1360 | 10000 | 0 | none | 2000 | 2.3 pF | 2.4 pF | 0.9 pF | `[koren_tube_lib_1996_mirror]` |
| Koren 12AX7 in the 2008 LTspice port | 100 | 1.4 | 1060 | 600 | 300 | 0.00 | 2000 | 2.3 pF | 2.4 pF | 0.9 pF | `[koren_tubes_lib_ltspice_2008]` |
| 12AX7A re-fit to the RCA sheet (2008) | 100.26 | 1.394 | 1651.8 | 17950.75 | 524.4 | 0.50 | 2000 | 2.3 pF | 2.4 pF | 0.9 pF | `[koren_tubes_lib_ltspice_2008]` |
| 12AX7 re-fit to Sylvania 1955 (2008) | 105.78 | 1.474 | 1618.2 | 432.76 | 35.6 | 0.50 | 2000 | 2.3 pF | 2.4 pF | 0.9 pF | `[koren_tubes_lib_ltspice_2008]` |

- **VCT** is a grid contact potential added to V_GK inside E1. It is not in Koren's original; it was introduced by the 2008 port `[koren_tubes_lib_ltspice_2008]`.
- The two 2008 re-fits land on very different KP/KVB pairs. The same tube type fitted to different manufacturers' published curves gives different parameters. That is evidence of model and fit spread, not of unit-to-unit spread.

### A.3 Implementation notes for ngspice 47

- **Run Koren's PSpice library unchanged.** Add `set ngbehavior=ps` to `.spiceinit` `[ngspice_manual_v47]`. In that mode ngspice defines `.func pwr(x, a) { pow(x, a) }` and `.func pwrs(x, a) { sgn(x) * pow(x, a) }` `[ngspice_inpcompat_source]`. B-source `pow` uses |x| `[ngspice_manual_v47]`.
- **Pitfall: do not paste Koren's `G1` into a native B-source.**
  - Native ngspice `pwr()` is sign-preserving: `if (x1 < 0.0) y = (-pow(-x1, x2))` `[ngspice_manual_v47]`. That is PSpice's PWRS behaviour, not PWR.
  - `pwrs` appears in the manual only in the list of functions that PSPICE-compatibility mode adds.
  - Either use ps mode, or write the plate current explicitly, e.g. `I = V(7) > 0 ? 2*pow(V(7),EX)/KG1 : 0` (*derived* from the definitions above).
- **Pitfall: B-source `exp()` is capped.** Its argument is limited to 14 and continues linearly above that `[ngspice_manual_v47]`. With the 1996 12AX7 set (KP = 600, MU = 100), the argument is 600·(0.01 + V_GK/sqrt(300 + V_PK²)) (*derived*):
  - It stays ≤ 6 for V_GK ≤ 0.
  - It exceeds 14 only when V_GK > 0.0133·sqrt(300 + V_PK²): about +1.35 V at V_PK = 100 V and about +3.3 V at 250 V.
  - The cap therefore matters only under grid-conduction overdrive, for example in fault scenarios that shift bias positive.
- **Monte Carlo draws.** Use `agauss(nom, avar, sigma)` or `gauss(...)` in `.param` or in device cards. A random function placed in a device card draws a new value per instance `[ngspice_manual_v47]`.

### A.4 12AX7 / ECC83 manufacturer data: Philips ECC83 `[philips_ecc83_datasheet_1954]`

Sheets are dated 1953-06-06 to 1955-02-02; values were transcribed from the scanned pages.

| Quantity (per section) | Value |
|---|---|
| Heater | 6.3 V at 300 mA (parallel), or 12.6 V at 150 mA (series, pins 4-5) |
| Typical characteristics, V_a = 250 V | V_g = −2.0 V, I_a = 1.2 mA, S (g_m) = 1.6 mA/V, µ = 100, R_i (r_p) = 62.5 kΩ |
| Typical characteristics, V_a = 100 V | V_g = −1.0 V, I_a = 0.5 mA, S = 1.25 mA/V, µ = 100, R_i = 80 kΩ |
| Max plate voltage | V_a max 300 V (V_a0 max 550 V, cold) |
| Max plate dissipation | W_a max 1 W |
| Other limits | I_k max 8 mA; −V_g max 50 V; V_kf max 180 V; R_g max 2 MΩ with automatic bias |

Consistency check (*derived*): µ = S·R_i gives 1.6 mA/V × 62.5 kΩ = 100 and 1.25 mA/V × 80 kΩ = 100.

### A.5 Tube-to-tube spread and end of life

- Koren notes that his parameters are "based on published data sheets" and that "tubes vary from unit-to-unit and batch-to-batch" `[koren_model_instructions_web]` (search snippet only). This is qualitative and gives no σ.
- Wear-out mechanism: "Cathode depletion is the loss of emission after thousands of hours of normal use" `[wikipedia_vacuum_tube_mirror]` (secondary source).
- **GAP.** I found no fetchable source giving a quantitative tube-tester end-of-life threshold, such as g_m or emission below X % of nominal, or a production-spread σ for 12AX7 µ, g_m or r_p. Do not put a number into the build without a source.

---

## B. Semiconductors: data sheets and SPICE models

### B.1 hFE ranges from manufacturer data sheets

| Device | Condition | hFE min | hFE max | Source |
|---|---|---|---|---|
| 2N3904 (onsemi 2N3903/D Rev. 9, Aug 2021) | I_C = 0.1 mA, V_CE = 1 V | 40 | n/a | `[onsemi_2n3903_2n3904_datasheet]` |
| | I_C = 1 mA, V_CE = 1 V | 70 | n/a | same |
| | **I_C = 10 mA, V_CE = 1 V** | **100** | **300** | same |
| | I_C = 50 mA, V_CE = 1 V | 60 | n/a | same |
| | I_C = 100 mA, V_CE = 1 V | 30 | n/a | same |
| 2N3906 (onsemi 2N3906/D Rev. 4, Feb 2010) | I_C = 0.1 mA, V_CE = 1 V | 60 | n/a | `[onsemi_2n3906_datasheet]` |
| | I_C = 1 mA | 80 | n/a | same |
| | **I_C = 10 mA** | **100** | **300** | same |
| | I_C = 50 mA | 60 | n/a | same |
| | I_C = 100 mA | 30 | n/a | same |
| BD139 (ST, Rev 5, May 2008) | I_C = 5 mA, V_CE = 2 V | 25 | n/a | `[st_bd135_bd139_datasheet]` |
| | **I_C = 150 mA, V_CE = 2 V** | **40** | **250** | same |
| | I_C = 0.5 A, V_CE = 2 V | 25 | n/a | same |
| | gain group BD139-10 at 150 mA | 63 | 160 | same |
| | gain group BD139-16 at 150 mA | 100 | 250 | same |
| TIP31C (MOSPEC) | I_C = 1.0 A, V_CE = 4 V | 25 | n/a | `[mospec_tip31_datasheet]` |
| | I_C = 3.0 A, V_CE = 4 V | 10 | 50 | same |

The 2N3906 values are as printed in the onsemi 2N3906/D text layer. It is a PNP device, but the extracted text shows no minus signs. For the pulse-test conditions, see each data sheet.

Key ratings:

| Device | Ratings | Source |
|---|---|---|
| 2N3904 | V_CEO 40 V, I_C 200 mA | `[onsemi_2n3903_2n3904_datasheet]` |
| 2N3906 | V_CEO 40 V, I_C 200 mA, P_D 625 mW | `[onsemi_2n3906_datasheet]` |
| BD139 | V_CEO 80 V, I_C 1.5 A (I_CM 3 A), P_tot 12.5 W at T_c ≤ 25 °C | `[st_bd135_bd139_datasheet]` |
| TIP31C | V_CEO 100 V, I_C 3 A, P_D 40 W | `[mospec_tip31_datasheet]` |

**Pass transistor.** BD139 has both an ST data sheet and an onsemi SPICE model (B.2), so it is the better-documented pass device of the two. The TIP31 onsemi model found in a Micro-Cap library copy has BF ≈ 3656, which looks like a fit artefact, so it was not recorded.

### B.2 `.MODEL` / `.SUBCKT` text (verbatim)

**2N3904, onsemi.** MODPEX-generated, Aug 2001. Source: https://raw.githubusercontent.com/robo-fish/Volta/2d2c372826096380f0e4f0226469b4fd7f31e20d/app/resources/Models_OnSemi.lib `[onsemi_spice_models_volta]`, a file distributed "with permission of ON Semiconductor".

```spice
.MODEL ON.Semiconductor.2n3904 npn
+IS=1.26532e-10 BF=206.302 NF=1.5 VAF=1000
+IKF=0.0272221 ISE=2.30771e-09 NE=3.31052 BR=20.6302
+NR=2.89609 VAR=9.39809 IKR=0.272221 ISC=2.30771e-09
+NC=1.9876 RB=5.8376 IRB=50.3624 RBM=0.634251
+RE=0.0001 RC=2.65711 XTB=0.1 XTI=1
+EG=1.05 CJE=4.64214e-12 VJE=0.4 MJE=0.256227
+TF=4.19578e-10 XTF=0.906167 VTF=8.75418 ITF=0.0105823
+CJC=3.76961e-12 VJC=0.4 MJC=0.238109 XCJC=0.8
+FC=0.512134 CJS=0 VJS=0.75 MJS=0.5
+TR=6.82023e-08 PTF=0 KF=0 AF=1
```

**2N3906.** MODPEX-generated, Aug 7 2001. Source: https://raw.githubusercontent.com/hanhha/SPICELIB/30137cb80078ea40e7c4cbf66f05f9bd496fea24/2N3906.LIB `[onsemi_2n3906_modpex_model_mirror]`. The file itself carries no vendor name. onsemi provenance is corroborated because onsemi's `mmbt3906tt1_ON` model has identical parameters `[espice_onsemi_lib_mirror]`.

```spice
.MODEL q2n3906 pnp
+IS=7.75521e-12 BF=194.093 NF=1.35509 VAF=156.436
+IKF=0.0660057 ISE=1.88546e-12 NE=1.81673 BR=3.41317
+NR=1.5 VAR=5.86061 IKR=1.70599 ISC=7.64281e-10
+NC=1.92376 RB=6.48961 IRB=0.1 RBM=0.1
+RE=0.0001 RC=2.45044 XTB=0.1 XTI=1
+EG=1.05 CJE=6.11928e-12 VJE=0.4 MJE=0.248812
+TF=5.21843e-10 XTF=0.932702 VTF=9.1046 ITF=0.0106472
+CJC=6.85007e-12 VJC=0.4 MJC=0.279018 XCJC=0.9
+FC=0.478887 CJS=0 VJS=0.75 MJS=0.5
+TR=4.30605e-07 PTF=0 KF=0 AF=1
```

**BD139, onsemi** (Feb 2004). Source: https://raw.githubusercontent.com/robo-fish/Volta/2d2c372826096380f0e4f0226469b4fd7f31e20d/app/resources/Models_OnSemi.lib `[onsemi_spice_models_volta]`.

```spice
.MODEL ON.Semiconductor.bd139 npn
+IS=1e-09 BF=222.664 NF=0.85 VAF=36.4079
+IKF=0.166126 ISE=5.03418e-09 NE=1.45313 BR=1.35467
+NR=1.33751 VAR=142.931 IKR=1.66126 ISC=5.02557e-09
+NC=3.10227 RB=26.9143 IRB=0.1 RBM=0.1
+RE=0.000472454 RC=1.04109 XTB=0.727762 XTI=1.04311
+EG=1.05 CJE=1e-11 VJE=0.75 MJE=0.33
+TF=1e-09 XTF=1 VTF=10 ITF=0.01
+CJC=1e-11 VJC=0.75 MJC=0.33 XCJC=0.9
+FC=0.5 CJS=0 VJS=0.75 MJS=0.5
+TR=1e-07 PTF=0 KF=0 AF=1
```

**1N4148, Diodes Inc.** Source: https://raw.githubusercontent.com/AndrejTica/School/65cb5a6dd0395eb53b8f16ed4cafa47b25959b41/LTspice/extras/DIODES.COM/OTHER/spicemodels_switching_diodes.txt `[diodes_inc_switching_diode_spice]`.

```spice
*SRC=1N4148;DI_1N4148;Diodes;Si;  75.0V  0.300A  4.00ns   Diodes Inc. -
.MODEL DI_1N4148 D  ( IS=222p RS=68.6m BV=75.0 IBV=1.00u
+ CJO=4.00p  M=0.333 N=1.65 TT=5.76n )
```

**1N4148, LTspice `standard.dio`** (attributed to OnSemi). Source: https://raw.githubusercontent.com/vgreff/LTSpiceLibraries/8913bcc7bd392af5bc4ad8df433bb4477ff6b8e6/LTSpice/vglib/cmp/Original/standard.dio `[ltspice_standard_dio_mirror]`.

```spice
.model 1N4148 D(Is=2.52n Rs=.568 N=1.752 Cjo=4p M=.4 tt=20n Iave=200m Vpk=75 mfg=OnSemi type=silicon)
```

**1N4745A (16 V, 1 W) zener, Diodes Inc** (subcircuit; anode = node 1, cathode = node 2). Source: https://raw.githubusercontent.com/AndrejTica/School/65cb5a6dd0395eb53b8f16ed4cafa47b25959b41/LTspice/extras/DIODES.COM/ZENER/LIB/spicemodels_zener_diodes.txt `[diodes_inc_zener_spice]`.

```spice
*SRC=1N4745A;DI_1N4745A;Diodes;Zener 10V-50V; 16.0V  1.00W   Diodes Inc.
Zener
*SYM=HZEN
.SUBCKT DI_1N4745A  1 2
*        Terminals    A   K
D1 1 2 DF
DZ 3 1 DR
VZ 2 3 14.6
.MODEL DF D ( IS=25.7p RS=0.620 N=1.10
+ CJO=74.4p VJ=1.00 M=0.330 TT=50.1n )
.MODEL DR D ( IS=5.15f RS=0.897 N=1.80 )
.ENDS
```

**1N4744A (15 V) zener, Diodes Inc** `[diodes_inc_zener_spice]`:

```spice
.SUBCKT DI_1N4744A  1 2
*        Terminals    A   K
D1 1 2 DF
DZ 3 1 DR
VZ 2 3 13.7
.MODEL DF D ( IS=27.5p RS=0.620 N=1.10
+ CJO=78.3p VJ=1.00 M=0.330 TT=50.1n )
.MODEL DR D ( IS=5.49f RS=0.804 N=1.77 )
.ENDS
```

**Simplified alternatives, LTspice `standard.bjt`** (mfg=NXP) `[ltspice_standard_bjt_mirror]`:

```spice
.model 2N3904 NPN(IS=1E-14 VAF=100 Bf=300 IKF=0.4 XTB=1.5 BR=4 CJC=4E-12 CJE=8E-12 RB=20 RC=0.1 RE=0.1 TR=250E-9 TF=350E-12 ITF=1 VTF=2 XTF=3 Vceo=40 Icrating=200m mfg=NXP)
.model 2N3906 PNP(IS=1E-14 VAF=100 BF=200 IKF=0.4 XTB=1.5 BR=4 CJC=4.5E-12 CJE=10E-12 RB=20 RC=0.1 RE=0.1 TR=250E-9 TF=350E-12 ITF=1 VTF=2 XTF=3 Vceo=40 Icrating=200m mfg=NXP)
```

Notes:

- **Sanity check** (*derived*). Each model's BF falls inside its data-sheet hFE window:
  - 2N3904: BF = 206.3, within 100-300 at 10 mA.
  - 2N3906: BF = 194.1, within 100-300.
  - BD139: BF = 222.7, within 40-250.
  - BF is an ideal maximum-gain parameter, so the effective hFE at a given I_C will be lower; check with a DC sweep.
- **LTspice-only fields.** The LTspice lines carry informational fields (`Vceo`, `Icrating`, `Iave`, `Vpk`, `mfg`, `type`). ngspice provides an LTspice-compatibility translation for `.include`d libraries (`set ngbehavior=lt` or `ltps`) `[ngspice_manual_v47]`. Smoke-test that these models load in your ngspice build.
- **1N5246B (0.5 W, 16 V):** no SPICE model or data sheet was reachable (**GAP**). Use 1N4745A, which has both a data sheet and a model.

### B.3 Zener and switching-diode data sheet values

| Part | Value | Source |
|---|---|---|
| 1N4745A | V_Z nom 16 V at I_Ztest = 15.5 mA; tolerance ±5 % (A series); r_dif ≤ 16 Ω at I_Ztest (≤ 700 Ω at 0.25 mA); I_R ≤ 5 µA at 12.2 V; I_ZM 57 mA; P_tot 1 W at 50 °C | `[philips_1n4728a_1n4749a_datasheet]` |
| 1N4744A | V_Z nom 15 V at 17 mA; r_dif ≤ 14 Ω | `[philips_1n4728a_1n4749a_datasheet]` |
| 1N47xx without suffix | ±10 %; the "A" suffix means ±5 % | `[goodark_1n4728_1n4764_datasheet]` |
| 1N4148 (ROHM) | V_RM 100 V, V_R 75 V, I_O 150 mA, I_FSM (1 µs) 2 A; V_F ≤ 1.0 V at 10 mA; I_R ≤ 5.0 µA at 75 V; C_r 4 pF; t_rr 4 ns | `[rohm_1n4148_datasheet]` |

---

## C. Component tolerances

| Component | Tolerance to use | Evidence | Status |
|---|---|---|---|
| Metal-film resistor | ±1 % | "reasonable tolerance (0.5%, 1%, or 2%)" `[wikipedia_resistor_mirror]` | Secondary only. **GAP:** Vishay MRS25 and Yageo MFR data sheets were unreachable. |
| Carbon-film resistor | ±5 % | IEC 60062 letter code J = ±5 % is documented for capacitors `[wikipedia_film_capacitor_mirror]` | **GAP:** no carbon-film data sheet (Yageo CFR) was reachable. |
| Film capacitor (PET) | ±5 / ±10 / ±20 % (J / K / M) | IEC/EN 60062 codes; PET capacitance varies about ±5 % over the temperature range `[wikipedia_film_capacitor_mirror]` | Secondary. **GAP:** WIMA MKS2/MKS4 data sheet unreachable. |
| Aluminium electrolytic | ±20 % (M) | `[wikipedia_al_electrolytic_mirror]` | Secondary. **GAP:** Nichicon/Panasonic series data sheet unreachable. |
| Electrolytic end-of-life (ripple-life test) | C < 80 % C₀, **or** ESR > 200 % ESR₀, **or** DCL > DCL₀, or leakage/damage | `[siegen_pedc_lecture08_capacitors]` (university course) | Fetched |
| Electrolytic endurance-test degradation failure | ΔC > 30 %, **or** ESR/impedance/loss factor > 3× initial | `[wikipedia_al_electrolytic_mirror]` | Secondary |
| Potentiometer track | ±20 % (typical) | none | **GAP:** no Alpha or Bourns data sheet reachable. Treat ±20 % as an assumption. |
| Zener V_Z | ±5 % (A suffix); ±10 % (no suffix) | `[philips_1n4728a_1n4749a_datasheet]`, `[goodark_1n4728_1n4764_datasheet]`; "most widely used tolerances are 5% and 10%" `[wikipedia_zener_mirror]` | Data sheet |

The two end-of-life definitions differ: 20 % loss with 2× ESR versus 30 % loss with 3× ESR. Pick one as a declared project assumption and cite it.

---

## D. Instrument accuracy

| Instrument | Specification | Value | Source |
|---|---|---|---|
| Fluke 115 (and 117) DMM | DC V accuracy on the 600.0 mV, 6.000 V, 60.00 V and 600.0 V ranges | **±(0.5 % of reading + 2 counts)** | `[fluke_11x_manual_dcv_accuracy]`, `[fluke_117_dcv_accuracy]` |
| | Display | **6000 counts**; resolution 0.1 mV, 1 mV, 10 mV, 0.1 V | `[fluke_11x_manual_general_specs]`, `[fluke_11x_manual_dcv_accuracy]` |
| | Reference conditions | 1 year after calibration, 18-28 °C, 0-90 % RH; temperature coefficient 0.1 × spec per °C outside that band | `[fluke_117_dcv_accuracy]`, `[fluke_11x_manual_general_specs]` |
| Rigol DS1000Z (and DS1000Z-E) oscilloscope | DC gain accuracy | **±3 % of full scale at ≥ 10 mV/div**; ±4 % FS below 10 mV/div | `[rigol_ds1000z_user_guide_2014]`, `[rigol_ds1000ze_manual_de_2021]` |
| | DC offset accuracy (DS1000Z-E) | ±0.1 div ± 2 mV ± 1 % of offset value | `[rigol_ds1000ze_manual_de_2021]` |
| Siglent SDS1000X-E | DC gain accuracy | ±3.0 % (5 mV/div to 10 V/div); ±4.0 % (≤ 2 mV/div) | `[siglent_sds1000xe_extracted_specs]` (low confidence: LLM-extracted secondary) |

- The Fluke values were read from the Users Manual (March 2020, Table 6, p. 20), through verbatim excerpts in the calibration-atlas dataset.
- Worked example (*derived*): 15.00 V read on the 60.00 V range has an uncertainty of ±(0.075 V + 2 × 0.01 V) = ±0.095 V.
- The oscilloscope's ±3 % is specified relative to full scale, not to the reading.

---

## E. Failure modes and ageing

- **Aluminium electrolytics** `[siegen_pedc_lecture08_capacitors]`:
  - The electrolyte evaporates or degrades; capacitance falls, ESR rises, and open-circuit wear-out becomes likely.
  - Life model: L_op = M_v·L_b·2^((T_m − T_a)/10). Life roughly doubles for every 10 °C of internal-temperature reduction.
  - Open-circuit mechanisms: electrolyte loss, terminal failure, venting. Short-circuit mechanisms: oxide breakdown, over-voltage or thermal stress.
  - The Wikipedia mirror corroborates drying-out and parameter drift, and gives the 30 % / 3× endurance limits `[wikipedia_al_electrolytic_mirror]`.
- **Vacuum tubes:** cathode depletion, meaning loss of emission after thousands of hours, is gradual. Heater failures are sudden `[wikipedia_vacuum_tube_mirror]`.
- **Field failure data in fault dictionaries.** Hochwald & Bastian (1979) examine "actual field failure statistics" to decide which failures a DC fault dictionary can pre-model `[hochwald_bastian_1979]`.
- **Fault-rate priors in diagnosis.** Fault-rate-aware decision trees prioritise faults with higher fault rates `[shi_he_wang_2019_gmm_dt_access]`.
- **Open / short / drift percentages: GAP.** None of RIAC/Quanterion FMD-2016, MIL-HDBK-338B, the CDE application guide or the Nichicon/Rubycon notes was reachable, from origin or from any mirror found. **No percentage values are recorded**, and none should be put in the build until one of those documents is read.

---

## F. Analog fault-diagnosis literature (DOIs verified from IEEE metadata unless noted)

| Key | Reference | DOI |
|---|---|---|
| `bandler_salama_1985` | J. W. Bandler, A. E. Salama, "Fault diagnosis of analog circuits," *Proc. IEEE* 73(8):1279-1325, Aug 1985. Covers fault dictionary, parameter identification, fault verification and approximation approaches. | [10.1109/PROC.1985.13281](https://doi.org/10.1109/PROC.1985.13281) |
| `stenbakken_souders_stewart_1989` | G. N. Stenbakken, T. M. Souders, G. W. Stewart, "Ambiguity groups and testability," *IEEE TIM* 38(5):941-947, Oct 1989 | [10.1109/19.39034](https://doi.org/10.1109/19.39034) |
| `pattipati_alexandridis_1990` | K. R. Pattipati, M. G. Alexandridis, "Application of heuristic search and information theory to sequential fault diagnosis," *IEEE SMC* 20(4):872-887, 1990 | [10.1109/21.105086](https://doi.org/10.1109/21.105086) |
| `dekleer_williams_1987` | J. de Kleer, B. C. Williams, "Diagnosing multiple faults," *Artificial Intelligence* 32(1):97-130, 1987. Bibliographic record from an ACM reference list; the probe-selection content was **not** verified. | [10.1016/0004-3702(87)90063-4](https://doi.org/10.1016/0004-3702(87)90063-4) |
| `hochwald_bastian_1979` | W. Hochwald, J. Bastian, "A dc approach for analog fault dictionary determination," *IEEE TCAS* 26(7):523-529, 1979 | [10.1109/TCS.1979.1084665](https://doi.org/10.1109/TCS.1979.1084665) |
| `schreiber_1979` | H. Schreiber, "Fault dictionary based upon stimulus design," *IEEE TCAS* 26(7):529-537, 1979 | [10.1109/TCS.1979.1084666](https://doi.org/10.1109/TCS.1979.1084666) |
| `shi_he_wang_2019_gmm_dt_access` | J. Shi, Q. He, Z. Wang, "GMM clustering-based decision trees considering fault rate and cluster validity ...," *IEEE Access* 7:140637-140650, 2019 | [10.1109/ACCESS.2019.2943380](https://doi.org/10.1109/ACCESS.2019.2943380) |
| `shi_deng_wang_he_2020_dmic_tim` | J. Shi et al., "A combined method for analog circuit fault diagnosis based on dependence matrices and intelligent classifiers," *IEEE TIM* 69(3):782-793, 2020. Covers ambiguity groups. | [10.1109/TIM.2019.2905307](https://doi.org/10.1109/TIM.2019.2905307) |
| `he_he_li_2020_gan_tim` | W. He, Y. He, B. Li, "GANs with comprehensive wavelet feature for fault diagnosis of analog circuits," *IEEE TIM* 69(9):6640-6650, 2020 | [10.1109/TIM.2020.2969008](https://doi.org/10.1109/TIM.2020.2969008) |
| `gao_yang_jiang_2021_incipient_tim` | T. Gao, J. Yang, S. Jiang, "Incipient fault diagnosis ... GMKL-SVM and wavelet fusion features," *IEEE TIM* 70, 2021. Benchmarks: Sallen-Key, biquad, leapfrog. | [10.1109/TIM.2020.3024337](https://doi.org/10.1109/TIM.2020.3024337) |
| `cloete_stander_wilke_2022_access` | J. B. Cloete, T. Stander, D. N. Wilke, "Parametric circuit fault diagnosis through oscillation-based testing ...," *IEEE Access* 10:15671-15680, 2022. Tolerance variation, simulated data. | [10.1109/ACCESS.2022.3149324](https://doi.org/10.1109/ACCESS.2022.3149324) |
| `miao_2024_attention_fcn_access` | Y. Miao et al., "Analog circuit incipient fault detection based on attention mechanism and FCN," *IEEE Access*, 2024. Tolerance-induced class overlap. | [10.1109/ACCESS.2024.3403908](https://doi.org/10.1109/ACCESS.2024.3403908) |
| `vassios_2025_selftrained_tim` | V. D. Vassios et al., "A self-trained, low-complexity method for detecting faults in analog circuits," *IEEE TIM* 74, 2025 | [10.1109/TIM.2025.3542098](https://doi.org/10.1109/TIM.2025.3542098) |

None of these abstracts states "SPICE Monte Carlo" explicitly. Cloete et al. and Miao et al. state that component tolerance variation is the core difficulty and that results use simulated data.

## G. ML and statistics method references

| Key | Reference | DOI / ID |
|---|---|---|
| `guo_2017_calibration` | C. Guo, G. Pleiss, Y. Sun, K. Q. Weinberger, "On Calibration of Modern Neural Networks," ICML 2017. Temperature scaling. | arXiv:1706.04599 (no DOI; PMLR v70) |
| `naeini_cooper_hauskrecht_2015` | M. P. Naeini, G. F. Cooper, M. Hauskrecht, "Obtaining Well Calibrated Probabilities Using Bayesian Binning," AAAI-15. ECE is the bin-weighted average of \|acc − conf\|. | [10.1609/aaai.v29i1.9602](https://doi.org/10.1609/aaai.v29i1.9602) |
| `zadrozny_elkan_2002` | B. Zadrozny, C. Elkan, "Transforming Classifier Scores into Accurate Multiclass Probability Estimates," KDD 2002. Isotonic calibration. | [10.1145/775047.775151](https://doi.org/10.1145/775047.775151) |
| `ke_2017_lightgbm` | G. Ke et al., "LightGBM: A Highly Efficient Gradient Boosting Decision Tree," NIPS 2017, pp. 3149-3157 per the official README; some citations say 3146-3154 | no DOI |
| `friedman_2001_gbm` | J. H. Friedman, "Greedy function approximation: A gradient boosting machine," *Ann. Statist.* 29(5), 2001 | [10.1214/aos/1013203451](https://doi.org/10.1214/aos/1013203451) |
| `dempster_laird_rubin_1977` | A. P. Dempster, N. M. Laird, D. B. Rubin, "Maximum likelihood from incomplete data via the EM algorithm," *JRSS-B* 39(1), 1977 | [10.1111/j.2517-6161.1977.tb01600.x](https://doi.org/10.1111/j.2517-6161.1977.tb01600.x) |
| `schwarz_1978_bic` | G. Schwarz, "Estimating the Dimension of a Model," *Ann. Statist.* 6(2):461-464, 1978 | [10.1214/aos/1176344136](https://doi.org/10.1214/aos/1176344136) |
| `lindley_1956` | D. V. Lindley, "On a measure of the information provided by an experiment," *Ann. Math. Statist.* 27(4):986-1005, 1956 | [10.1214/aoms/1177728069](https://doi.org/10.1214/aoms/1177728069) |
| `mackay_1992_active_data_selection` | D. J. C. MacKay, "Information-based objective functions for active data selection," *Neural Computation* 4(4):590-604, 1992 | [10.1162/neco.1992.4.4.590](https://doi.org/10.1162/neco.1992.4.4.590) |
| `efron_1979_bootstrap` | B. Efron, "Bootstrap Methods: Another Look at the Jackknife," *Ann. Statist.* 7(1):1-26, 1979 | [10.1214/aos/1176344552](https://doi.org/10.1214/aos/1176344552) |
| `hanley_mcneil_1982_auc` | J. A. Hanley, B. J. McNeil, "The meaning and use of the area under a ROC curve," *Radiology* 143(1):29-36, 1982 | [10.1148/radiology.143.1.7063747](https://doi.org/10.1148/radiology.143.1.7063747) |
| `hendrycks_gimpel_2017_ood` | D. Hendrycks, K. Gimpel, "A Baseline for Detecting Misclassified and Out-of-Distribution Examples in Neural Networks," ICLR 2017 | arXiv:1610.02136 (no DOI) |

Implementation note `[sklearn_calibration_user_guide]`:

- scikit-learn's `CalibratedClassifierCV` supports `method="temperature"`, alongside sigmoid and isotonic.
- T is fitted by minimising log loss on a hold-out set, and does not change accuracy.
- Isotonic calibration is advised only with more than about 1000 calibration samples.

---

## H. Circuit references and tooling

- **Baxandall (1952):** P. J. Baxandall, "Negative-feedback tone control," *Wireless World*, Oct 1952, pp. 402-405. Bibliographic details only `[baxandall_1952_bibliographic]`.
  - **GAP:** neither the article PDF nor an authoritative description of the *passive* Baxandall tone stack was reachable. ESP, Douglas Self's *Small Signal Audio Design* and Duncan Amps TSC were all blocked.
- **Capacitor-input filter ripple:** V_pp = I/(2fC) for full-wave, and I/(fC) for half-wave. This assumes CR is much larger than the period, so the capacitor discharges almost linearly between peaks `[wikipedia_ripple_mirror]`. The Wikipedia text cites Millman & Halkias, *Integrated Electronics* (1972), pp. 112-114.
  - Horowitz & Hill, *The Art of Electronics* 3rd ed. (Cambridge University Press, 2015, ISBN 9780521809269) is confirmed bibliographically `[horowitz_hill_2015_aoe3]`. Its ripple page was not reachable.

### ngspice 47

ngspice 47 is the current release (2026-08-11) `[ngspice_manual_v47]`, `[ngspice_release_notes_47]`. Manual: https://sourceforge.net/projects/ngspice/files/ng-spice-rework/47/ngspice-47-manual.pdf/download

| Section | Topic |
|---|---|
| Ch. 5 (p. 105) | B, E and G behavioural sources (`BXXXXXXX n+ n- <i=expr> <v=expr> ...`; `EXXXXXXX n+ n- value={expr}`) |
| 12.11.5 / 12.11.6 | PSPICE and LTSPICE compatibility modes |
| 13.5.3 (p. 398) | `alter`, including devices inside subcircuits; see also `altermod` and `alterparam` |
| 11.6.4 (p. 353) | `.four`, batch mode only |
| 13.5.35 (p. 414) | `fourier`: DC plus 9 harmonics by default; TMAX ≤ period·nperiods/100 |
| 1.4 (p. 45) | Convergence: RELTOL default 10⁻³ |
| 11.1.2 | `GMIN` default 1e-12; `GMINSTEPS`, `SRCSTEPS` |
| 11.3.5 (p. 331) | Convergence aids in order: gmin stepping (default: two processes in series), source stepping (default: Gillespie), then optional `optran` transient operating point |
| 18.2 (p. 549) | Statistical functions `gauss`, `agauss`, `unif`, `aunif`, `limit` |


### schemdraw

- **schemdraw 0.23** (2026-05-29, MIT, Python ≥ 3.9) `[schemdraw_pypi]`, `[schemdraw_docs]`:
  - Since 0.22 it has `VacuumTube`, `Triode`, `Tetrode`, `Pentode` and `DualVacuumTube` elements, with functional anchors such as `control`.
  - Docs are at schemdraw.readthedocs.io; that site was blocked, so the docs were read from the GitHub `docs/` sources.

---

## I. Anthropic API (checked live on platform.claude.com, 2026-09-28)

| Class | Current model ID | Price per MTok (input / output) | Notes | Source |
|---|---|---|---|---|
| Sonnet | **`claude-sonnet-5-5`** | **$2 / $10** | Released 2026-09-28; 1M context, 128K output. Cache read $0.20, 5 m cache write $2.50, 1 h cache write $4. | `[claude_sonnet_5_5_overview]`, `[claude_pricing]` |
| Opus | **`claude-opus-5-5`** | **$4 / $20** | Released 2026-09-22; cache read $0.20. | `[claude_opus_5_5_overview]`, `[claude_pricing]` |
| Other current models | `claude-fable-5-1`, `claude-haiku-4-5` (ID `claude-haiku-4-5-20251001`) | $10 / $50 and $1 / $5 | | `[claude_models_overview]` |

- **Pricing modifiers:** the Batch API is 50 % off. Cache reads cost 10 % of base input: 5 % on Opus 5.5, 2.5 % on Fable 5.1 `[claude_models_overview]`.
- **Tool use:** see `[claude_tool_use_overview]`. `strict: true` guarantees schema-valid tool calls.
  - **Sonnet 5.5 does not support forced tool use.** `tool_choice` `any` or `tool` returns a 400 `[claude_sonnet_5_5_whats_new]`. Use `auto` with strict tools, or structured outputs.
- **Structured outputs:** use `output_config.format` with `type: json_schema` `[claude_structured_outputs]`.
  - Numerical constraints (`minimum`, `maximum`, `multipleOf`) and string-length constraints are **not** supported, so validate numeric ranges (e.g. component values) client-side.
  - Objects need `additionalProperties: false`.
- **Vision:** JPEG, PNG, GIF and WebP; at most 8000 × 8000 px, and 10 MB per image on the API `[claude_vision]`.
  - Cost is ⌈w/28⌉ × ⌈h/28⌉ visual tokens.
  - Claude 4.7+ models accept up to a 2576 px long edge before downscaling.
- **Prompt caching:** minimum cacheable prefix of 512 tokens for Opus 5.5 and Sonnet 5.5; up to 4 breakpoints; 5-minute default TTL, 1-hour TTL at 2× input price `[claude_prompt_caching]`, `[claude_pricing]`.

---

## Gaps and follow-ups

These need to be fetched once the listed hosts are allowed, or supplied by the team.

1. **Failure-mode percentages** (open / short / drift) for resistors, film and electrolytic capacitors, diodes and BJTs. Needs RIAC/Quanterion FMD-2016 or MIL-HDBK-338B (everyspec.com, quicksearch.dla.mil). **None recorded.**
2. **Tube end-of-life thresholds** (tube-tester g_m or emission as % of nominal) and a quantitative 12AX7 production spread. Needs e.g. Hickok or TV-7 manuals, or MIL-E-1 12AX7WA acceptance limits.
3. **Passive-component data sheets:**
   - Vishay MRS25 / Yageo MFR (±1 %) and Yageo CFR (±5 %)
   - WIMA MKS2/MKS4 tolerance options
   - Nichicon or Panasonic electrolytic series: ±20 %, tan δ limit, endurance criteria
   - Alpha or Bourns potentiometer track tolerance (±20 %)
   - Current values rest on secondary sources (Wikipedia mirrors) or are unverified assumptions.
4. **Primary Koren article text** (normankoren.com; equations seen only as a search snippet). The verbatim library listing is fetched and is the operative definition.
5. **Other items:**
   - Siglent SDS1000X-E data sheet: only an LLM-extracted secondary was fetched.
   - 1N5246B data sheet and model.
   - Passive Baxandall tone-stack description.
   - Horowitz & Hill ripple page.
   - de Kleer & Williams probe-selection content.
   - Most IEEE and ML papers were verified at the metadata level only.
