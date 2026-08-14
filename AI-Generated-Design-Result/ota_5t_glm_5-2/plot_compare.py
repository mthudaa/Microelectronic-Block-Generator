"""Pre vs post comparison plots."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

WD = "/tmp/opencode/mbg_ota_5t"

def parse_dat(path):
    cols = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("#","*","@")): continue
            parts = line.split()
            try: cols.append([float(x) for x in parts])
            except ValueError: pass
    arr = np.array(cols)
    return {"sweep": arr[:,0], **{f"c{i}": arr[:, i] for i in range(1, arr.shape[1])}}

fig = plt.figure(figsize=(10,8))

# 1) Bode (gain) comparison
ax1 = fig.add_subplot(3,1,1)
for path, label, color in [(f"{WD}/pre_ac.dat","Pre-layout","tab:blue"),
                           (f"{WD}/post_ac.dat","Post-layout (PEX)","tab:red")]:
    a = parse_dat(path)
    mag = 20*np.log10(np.sqrt(a["c1"]**2 + a["c2"]**2) + 1e-30)
    ax1.semilogx(a["sweep"], mag, lw=1.5, label=label, color=color)
ax1.set_ylabel("Gain [dB]"); ax1.grid(True, which="both", ls=":", alpha=0.4)
ax1.set_title("AC magnitude comparison - ota_5t")
ax1.axhline(0, ls="-", color="k", lw=0.5)
ax1.legend(loc="upper right")

# 2) DC transfer (offset/linearity)
ax2 = fig.add_subplot(3,1,2)
for path, label, color in [(f"{WD}/pre_dc.dat","Pre-layout","tab:blue"),
                           (f"{WD}/post_dc.dat","Post-layout","tab:red")]:
    d = parse_dat(path)
    ax2.plot(d["sweep"]*1e3, d["c1"], lw=1.5, label=label, color=color)
ax2.set_xlabel("Diff-input [mV]"); ax2.set_ylabel("Vout [V]"); ax2.legend()
ax2.grid(True, ls=":", alpha=0.5)
ax2.set_title("DC transfer comparison")

# 3) TRAN
ax3 = fig.add_subplot(3,1,3)
for path, label, color in [(f"{WD}/pre_tran.dat","Pre-layout V(out)","tab:blue"),
                           (f"{WD}/post_tran.dat","Post-layout V(out)","tab:red")]:
    t = parse_dat(path)
    ax3.plot(t["sweep"]*1e6, t["c1"], lw=1.5, label=label, color=color)
ax3.set_xlabel("Time [µs]"); ax3.set_ylabel("Vout [V]"); ax3.legend()
ax3.grid(True, ls=":", alpha=0.5)
ax3.set_title("TRAN comparison")

fig.tight_layout()
fig.savefig(f"{WD}/compare_pre_post.png", dpi=130)
plt.close(fig)
print(f"Saved {WD}/compare_pre_post.png")
