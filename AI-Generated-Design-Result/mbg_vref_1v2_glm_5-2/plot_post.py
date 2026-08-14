#!/usr/bin/env python3
"""Post-layout analysis: PNG plots + pre/post comparison + deviation metrics."""
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

def get_series(prefix, kind, xkeys, ykeys):
    p = os.path.join(WD, f"{prefix}_{kind}.raw")
    names, data, _ = parse_raw(p)
    xi = find_idx(names, xkeys)
    yi = find_idx(names, ykeys)
    return np.array([d[xi] for d in data]), np.array([d[yi] for d in data]), names

# DC sweeps
vdd_pre,  vref_dc_pre,  _ = get_series("vref",      "dc",   ["v(vdd)"], ["v(vref)"])
vdd_post, vref_dc_post, _ = get_series("vref_post", "dc",   ["v(vdd)"], ["v(vref)"])
# Temperature sweeps
temp_pre,  vref_t_pre,  _ = get_series("vref",      "temp", ["temp-sweep","temp"], ["v(vref)"])
temp_post, vref_t_post, _ = get_series("vref_post", "temp", ["temp-sweep","temp"], ["v(vref)"])
# Transient
tm_pre,  vref_x_pre,  _ = get_series("vref",      "tran", ["time"], ["v(vref)"])
tm_post, vref_x_post, _ = get_series("vref_post", "tran", ["time"], ["v(vref)"])
tm_pre *= 1e6; tm_post *= 1e6

# Nominal values @ 27C, VDD=3.3
def at_value(xs, ys, val):
    j = int(np.argmin(np.abs(xs - val)))
    return float(ys[j])
vref_pre_27  = at_value(temp_pre,  vref_t_pre,  27)
vref_post_27 = at_value(temp_post, vref_t_post, 27)
vref_pre_3v3  = at_value(vdd_pre,  vref_dc_pre,  3.3)
vref_post_3v3 = at_value(vdd_post, vref_dc_post, 3.3)
dev_27   = abs(vref_post_27  - vref_pre_27)  / abs(vref_pre_27)  * 100
dev_3v3  = abs(vref_post_3v3 - vref_pre_3v3) / abs(vref_pre_3v3) * 100
# Tempco pre/post
pre_max, pre_min  = float(vref_t_pre.max()),  float(vref_t_pre.min())
post_max, post_min = float(vref_t_post.max()), float(vref_t_post.min())
tc_pre  = (pre_max  - pre_min)  / (vref_pre_27  * 165) * 1e6
tc_post = (post_max - post_min) / (vref_post_27 * 165) * 1e6
pass_10pct = (dev_27 <= 10.0) and (dev_3v3 <= 10.0)

# ---- POST DC ----
fig, ax = plt.subplots(figsize=(8,5))
ax.plot(vdd_post, vref_dc_post, 'r-', lw=2, label="Post-Layout (PEX) Vref")
ax.axhline(1.2, color='gray', ls='--', lw=1, alpha=0.6, label="Target 1.2V")
ax.set_xlabel("VDD (V)"); ax.set_ylabel("Vref (V)")
ax.set_title("Post-Layout: Vref vs VDD"); ax.legend(); ax.grid(True, alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(WD, "plot_post_dc.png"), dpi=150); plt.close(fig)
# ---- POST TEMP ----
fig, ax = plt.subplots(figsize=(8,5))
ax.plot(temp_post, vref_t_post, 'r-', lw=2, label="Post-Layout (PEX) Vref")
ax.set_xlabel("Temperature (degC)"); ax.set_ylabel("Vref (V)")
ax.set_title("Post-Layout: Vref vs Temperature (-40..125C)"); ax.legend(); ax.grid(True, alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(WD, "plot_pre_temp.png").replace("pre","post"), dpi=150); plt.close(fig)
# ensure correct post tran name
fig.savefig(os.path.join(WD, "plot_post_temp.png"), dpi=150); plt.close(fig) if False else None
# ---- POST TRAN ----
fig, (a1,a2) = plt.subplots(2,1, figsize=(8,6), sharex=True)
a2.plot(tm_post, vref_x_post, 'r', lw=2, label="Vref")
a2.axhline(1.2, color='gray', ls='--', lw=1, alpha=0.6)
a2.set_xlabel("Time (us)"); a2.set_ylabel("Vref (V)"); a2.legend(); a2.grid(True, alpha=0.3)
a1.set_title("Post-Layout: Power-Up Transient"); a1.grid(True, alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(WD, "plot_post_tran.png"), dpi=150); plt.close(fig)
# ---- COMPARE overlay (DC + TEMP) ----
fig, (a1,a2) = plt.subplots(2,1, figsize=(8,8))
a1.plot(vdd_pre, vref_dc_pre, 'b-', lw=2, label="Pre-Layout")
a1.plot(vdd_post, vref_dc_post, 'r--', lw=2, label="Post-Layout (PEX)")
a1.axhline(1.2, color='gray', ls=':', lw=1, alpha=0.5)
a1.set_xlabel("VDD (V)"); a1.set_ylabel("Vref (V)"); a1.set_title("Pre vs Post-Layout: Vref vs VDD")
a1.legend(); a1.grid(True, alpha=0.3)
a2.plot(temp_pre, vref_t_pre, 'b-', lw=2, label="Pre-Layout")
a2.plot(temp_post, vref_t_post, 'r--', lw=2, label="Post-Layout (PEX)")
a2.set_xlabel("Temperature (degC)"); a2.set_ylabel("Vref (V)"); a2.set_title("Pre vs Post-Layout: Vref vs Temperature")
a2.legend(); a2.grid(True, alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(WD, "plot_compare.png"), dpi=150); plt.close(fig)

cmp = (
    f"PRE/POST-LAYOUT COMPARISON (vref_1v2)\n"
    f"PRE_VREF_27C   = {vref_pre_27:.4f} V\n"
    f"POST_VREF_27C  = {vref_post_27:.4f} V\n"
    f"DELTA_27C      = {abs(vref_post_27-vref_pre_27)*1000:.3f} mV\n"
    f"DEVIATION_27C  = {dev_27:.3f} %\n"
    f"PRE_VREF_3.3V  = {vref_pre_3v3:.4f} V\n"
    f"POST_VREF_3.3V = {vref_post_3v3:.4f} V\n"
    f"DEVIATION_3.3V = {dev_3v3:.3f} %\n"
    f"PRE_TEMPCO     = {tc_pre:.1f} ppm/C\n"
    f"POST_TEMPCO    = {tc_post:.1f} ppm/C\n"
    f"PASS_10PCT     = {pass_10pct}\n"
)
print(cmp)
with open(os.path.join(WD, "comparison.txt"), "w") as f:
    f.write(cmp)
print("Saved plot_post_dc.png, plot_post_temp.png, plot_post_tran.png, plot_compare.png, comparison.txt")
