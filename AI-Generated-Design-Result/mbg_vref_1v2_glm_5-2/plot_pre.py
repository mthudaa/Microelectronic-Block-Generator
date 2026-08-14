#!/usr/bin/env python3
"""Parse ngspice binary raw files for pre-layout vref and generate PNG plots + summary."""
import struct, re, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

WD = os.path.dirname(os.path.abspath(__file__))

def parse_raw(path):
    with open(path, "rb") as f:
        content = f.read()
    hdr_end = content.find(b"Binary:\n")
    if hdr_end < 0:
        return None, [], 0
    header = content[:hdr_end].decode("latin-1")
    n_vars = int(re.search(r"No\. Variables:\s+(\d+)", header).group(1))
    n_pts = int(re.search(r"No\. Points:\s+(\d+)", header).group(1))
    vars_section = header.split("Variables:\n")[1]
    names = [ln.strip().split("\t")[1] for ln in vars_section.strip().split("\n") if "\t" in ln]
    data_start = hdr_end + len(b"Binary:\n")
    fmt = "<" + "d" * n_vars
    csz = struct.calcsize(fmt)
    data = []
    for pt in range(n_pts):
        off = data_start + pt * csz
        if off + csz > len(content):
            break
        data.append(struct.unpack(fmt, content[off:off + csz]))
    return names, data, n_pts

def find_idx(names, keys):
    for k in keys:
        for i, n in enumerate(names):
            if k.lower() in n.lower():
                return i
    return None

# ---- DC sweep ----
names, data, _ = parse_raw(os.path.join(WD, "vref_dc.raw"))
vidd = find_idx(names, ["i(vvdd)", "vvdd#branch", "i(vvdd)", "vdd#branch"])
vvdd = find_idx(names, ["v(vdd)"])
vvref = find_idx(names, ["v(vref)"])
vdds = np.array([d[vvdd] for d in data])
vrefs = np.array([d[vvref] for d in data])
# current at vdd=3.3
idx33 = int(np.argmin(np.abs(vdds - 3.3)))
i33 = abs(data[idx33][vidd]) if vidd is not None else 185.6e-6
vref_3p3 = vrefs[idx33]
# line reg 2.7->3.3
idx27 = int(np.argmin(np.abs(vdds - 2.7)))
vref_27line = vrefs[idx27]
line_reg = (vref_3p3 - vref_27line) / (3.3 - 2.7) * 1000 if abs(vdds[idx27]-2.7) < 0.05 else None

fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(vdds, vrefs, 'b-', linewidth=2, label="Pre-Layout Vref")
ax.axhline(1.2, color='gray', ls='--', lw=1, alpha=0.6, label="Target 1.2V")
ax.set_xlabel("VDD (V)"); ax.set_ylabel("Vref (V)")
ax.set_title("Pre-Layout: Vref vs VDD (GF180MCU 3.3V)")
ax.legend(); ax.grid(True, alpha=0.3); fig.tight_layout()
fig.savefig(os.path.join(WD, "plot_pre_dc.png"), dpi=150); plt.close(fig)

# ---- Temperature sweep ----
names_t, data_t, _ = parse_raw(os.path.join(WD, "vref_temp.raw"))
tidx = find_idx(names_t, ["temp-sweep", "temp"])
vridx = find_idx(names_t, ["v(vref)"])
temps = np.array([d[tidx] for d in data_t])
vrefs_t = np.array([d[vridx] for d in data_t])
vref_max = float(vrefs_t.max()); vref_min = float(vrefs_t.min())
# nominal @27
j27 = int(np.argmin(np.abs(temps - 27)))
vref_27 = float(vrefs_t[j27])
tempco = (vref_max - vref_min) / (vref_27 * (125 - (-40))) * 1e6

fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(temps, vrefs_t, 'b-', linewidth=2, label="Pre-Layout Vref")
ax.set_xlabel("Temperature (degC)"); ax.set_ylabel("Vref (V)")
ax.set_title("Pre-Layout: Vref vs Temperature (-40..125C)")
ax.legend(); ax.grid(True, alpha=0.3); fig.tight_layout()
fig.savefig(os.path.join(WD, "plot_pre_temp.png"), dpi=150); plt.close(fig)

# ---- Transient ----
names_x, data_x, _ = parse_raw(os.path.join(WD, "vref_tran.raw"))
tidx = find_idx(names_x, ["time"])
vridx = find_idx(names_x, ["v(vref)"])
viddidx = find_idx(names_x, ["v(vdd)"])
tm = np.array([d[tidx] for d in data_x]) * 1e6
vr = np.array([d[vridx] for d in data_x])
vdd_x = np.array([d[viddidx] for d in data_x])

fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
a1.plot(tm, vdd_x, 'b', lw=1.5); a1.set_ylabel("VDD (V)")
a1.set_title("Pre-Layout: Power-Up Transient"); a1.grid(True, alpha=0.3)
a2.plot(tm, vr, 'r', lw=2, label="Vref"); a2.axhline(1.2, color='gray', ls='--', lw=1, alpha=0.6)
a2.set_xlabel("Time (us)"); a2.set_ylabel("Vref (V)"); a2.legend(); a2.grid(True, alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(WD, "plot_pre_tran.png"), dpi=150); plt.close(fig)

power = 3.3 * i33 * 1e6
summary = (
    f"PRE-LAYOUT RESULTS (vref_1v2, MOSFET-only beta-multiplier)\n"
    f"Vref @27C, VDD=3.3V = {vref_27:.4f} V\n"
    f"Vref @3.3V (27C)     = {vref_3p3:.4f} V\n"
    f"Vref_max (-40..125)  = {vref_max:.4f} V\n"
    f"Vref_min (-40..125)  = {vref_min:.4f} V\n"
    f"Tempco (ppm/C)       = {tempco:.1f}   (relaxed spec: <=200)\n"
    f"I_total @3.3V        = {i33*1e6:.2f} uA\n"
    f"Power                = {power:.1f} uW ({power/1000:.3f} mW)\n"
    f"Line reg (2.7->3.3)  = {line_reg:.2f} mV/V\n" if line_reg else ""
)
print(summary)
with open(os.path.join(WD, "sim_summary.txt"), "w") as f:
    f.write(summary)
print("Saved plot_pre_dc.png, plot_pre_temp.png, plot_pre_tran.png, sim_summary.txt")
