"""Parse post-layout wrdata text files and save PNG plots."""
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

# Post AC
ac = parse_dat(f"{WD}/post_ac.dat")
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9,6), sharex=True)
freq = ac["sweep"]
mag = 20*np.log10(np.sqrt(ac["c1"]**2 + ac["c2"]**2) + 1e-30)
phase_deg = np.degrees(ac["c5"])
ax1.semilogx(freq, mag, lw=1.5, color="tab:red")
ax1.set_ylabel("|Vout| [dB]"); ax1.grid(True, which="both", ls=":", alpha=0.4)
ax1.set_title("Post-layout (PEX C-coupled) AC analysis - ota_5t (GF180MCU 3.3V)")
ax2.semilogx(freq, phase_deg, lw=1.5, color="tab:green")
ax2.set_xlabel("Frequency [Hz]"); ax2.set_ylabel("Phase [°]"); ax2.grid(True, which="both", ls=":", alpha=0.4)
fig.tight_layout(); fig.savefig(f"{WD}/post_ac.png", dpi=130); plt.close(fig)
print(f"Saved {WD}/post_ac.png  | flat gain ≈ {mag[0]:.2f} dB at {freq[0]:.1f} Hz")

# Post DC
dc = parse_dat(f"{WD}/post_dc.dat")
vp = dc["sweep"]; vout = dc["c1"]
fig, ax = plt.subplots(figsize=(9,4))
ax.plot(vp*1e3, vout, lw=1.5, color="tab:red")
ax.set_xlabel("Differential input [mV]"); ax.set_ylabel("Vout [V]")
ax.set_title("Post-layout DC transfer - ota_5t")
ax.grid(True, ls=":", alpha=0.5)
fig.tight_layout(); fig.savefig(f"{WD}/post_dc.png", dpi=130); plt.close(fig)
i0 = np.argmin(np.abs(vp-0))
slope = (vout[i0+3]-vout[i0-3])/(vp[i0+3]-vp[i0-3])
print(f"Saved {WD}/post_dc.png  | DC gain ≈ {20*np.log10(abs(slope)):.2f} dB at Vout={vout[i0]:.4f}V")

# Post TRAN
tran = parse_dat(f"{WD}/post_tran.dat")
t = tran["sweep"]; vout_t = tran["c1"]; vin_t = tran["c3"]*1e3
fig, ax = plt.subplots(figsize=(9,4))
ax.plot(t*1e6, vout_t, lw=1.5, color="tab:red", label="Vout")
ax.plot(t*1e6, vin_t, lw=1.0, ls="--", color="k", label="Vin (diff, mV)")
ax.set_xlabel("Time [µs]"); ax.set_ylabel("Voltage [V]")
ax.set_title("Post-layout TRAN response - ota_5t")
ax.legend(); ax.grid(True, ls=":", alpha=0.5)
fig.tight_layout(); fig.savefig(f"{WD}/post_tran.png", dpi=130); plt.close(fig)
print(f"Saved {WD}/post_tran.png | output swing = {(vout_t.max()-vout_t.min())*1e3:.2f} mV")

print("DONE")
