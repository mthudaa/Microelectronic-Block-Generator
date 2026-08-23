# ox-alpha OTA — PVT and Extended Characterization

Post-flow characterization of the **final extracted (PEX) netlist**
(`final/ota.pex.spice`), run outside the `/mbg-full-auto` gate because the
flow does not configure PVT/Monte-Carlo conditions. Raw data:
`pvt/pvt_summary.json`, `pvt/characterization.json`, per-point decks under
`pvt/`. Scripts: `scripts/pvt_char.py`.

Nominal operating point: VDD = 3.3 V, IBIAS = 20 uA, VIN_CM = 1.65 V,
CL = 5 pF, 27 C.

## PVT grid — 45 points (VDD x TEMP x process corner)

Corners: typical, ff, ss, fs, sf. Temps: -40 / 27 / +125 C. VDD: 3.0 / 3.3 / 3.6 V.
All 45 points produced full data.

| Metric | Range over grid | Required | Verdict |
|---|---|---|---|
| DC gain | 48.1 – 51.9 dB | >= 35 dB | PASS everywhere |
| GBW (unity-gain freq) | 3.22 – 6.14 MHz | >= 1 MHz | PASS everywhere |
| Phase margin | 82.8 – 85.5 deg | >= 60 deg | PASS everywhere |
| Supply current IDD | 52.0 – 66.0 uA | <= 250 uA | PASS everywhere |
| Slew rate (corner spots, rise/fall) | 7.7 – 12.7 V/us | >= 0.5 V/us | PASS at all 6 spots |
| Output DC (zero differential input) | 1.52 – 2.45 V | 1.15 – 2.15 V | see caveat |

**Output-DC caveat (honest):** OUT_DC ~= VDD − |VGS_P| by construction of the
mirror load, so it tracks the supply rail. The ±0.5 V window holds across
every corner at VDD = 3.0 V (max 1.845 V) and at VDD = 3.3 V (max 2.145 V,
right at the edge), but at **VDD = 3.6 V** OUT_DC leaves the window in most
corners (up to 2.445 V at ff/125 C). The stage remains functional there; only
the DC-centering spec is exceeded on the high line. Fixing this properly needs
a topology change (e.g. supply-independent bias of the load VGS or a
common-mode feedback loop) — recorded as a known limitation, not silently
passed.

Worst cases:

- gain: fs / 3.0 V / 125 C -> 48.06 dB
- GBW: ss / 3.0 V / 125 C -> 3.22 MHz
- PM: ff / 3.6 V / -40 C -> 82.76 deg
- IDD max: ff / 3.6 V / -40 C -> 66.0 uA

## Extended characterization (nominal corner)

| Quantity | Value | Method |
|---|---|---|
| CMRR (DC) | 74.3 dB | AC common-mode sweep vs differential gain |
| PSRR+ (DC) | ~50.4 dB (= ADM; AVDD->OUT ~ 0 dB, mirror-load OTA property) | AC on VDD |
| ICMR | [0.28, 2.34] V @ >=50% peak diff gain; [0.30, 1.48] V @ -3 dB criterion | +/-5 mV dither, VICM sweep |
| Input-referred noise | 278 uV rms integrated 10 Hz – 100 MHz (ngspice `inoise_total`) | `.noise` |
| Input-referred offset (mismatch MC, n=25) | sigma ~ 1.6–1.8 mV (sigma_OUT ~ 0.55–0.60 V / ADM 333) | GF180 statistical corner, sw_stat_mismatch=1 |
| Systematic (schematic vs PEX OUT_DC shift) | ~6 uV input-referred (2 mV / 333) | OP comparison |

Notes, stated plainly:

- PSRR+ of a single-stage mirror-load OTA equals ADM at DC because the output
  follows VDD minus a fixed VGS; this is expected physics for this topology,
  not a measurement error.
- The MC offset estimate is not seed-reproducible: the PDK's per-instance
  `agauss` draws ignore `set seed` in `.control` on this ngspice build
  (verified empirically). Each run is an independent 25-sample estimate.
- On the **extracted** netlist, mismatch Monte Carlo returns zero spread: the
  Magic PEX deck style (`.option scale=5n` with unscaled numeric instance
  parameters) disables the statistical wrapper's draws. Offset was therefore
  characterized on the schematic netlist; the systematic layout component is
  covered by the schematic-vs-PEX comparison above.
- Usable swing (nominal, from the flow's own measurement): within -6 dB of
  peak incremental gain the output spans **[1.97, 2.91] V**; the absolute
  large-signal traversal is **[0.49, 3.30] V**, which contains the requested
  0.5–2.8 V interval. A single-ended NMOS-input pair at VIN_CM = 1.65 V
  cannot hold gain down to 0.5 V (output floor ~ VICM − VT_N); this is a
  topology limit reported as characterized data (`swing_low_v` FAIL is
  non-required by design), not as a pass.
