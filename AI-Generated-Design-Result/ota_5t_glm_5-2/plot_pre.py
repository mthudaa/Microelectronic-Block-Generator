"""Parse wrdata text files and save PNG plots."""
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
    if not cols:
        raise RuntimeError(f"Empty data file: {path}")
    arr = np.array(cols)
    n = arr.shape[1]
    # wrdata: sweep, real, imag, real, imag, ...
    data = {"sweep": arr[:,0]}
    for i in range(1, n):
        data[f"c{i}"] = arr[:, i]
    return data


# ---------- Pre-layout AC ----------
ac = parse_dat(f"{WD}/pre_ac.dat")
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9,6), sharex=True)
freq = ac["sweep"]
# wrdata for v(out) -> c1 (real), c2 (imag); vdb(out) -> c3(real), c4(imag); vp(out) -> c5(real), c6(imag)
mag = 20*np.log10(np.sqrt(ac["c1"]**2 + ac["c2"]**2) + 1e-30)
# phase in deg: c5 is real part of vp (which is stored in rad)
phase_rad = ac["c5"]
phase_deg = np.degrees(phase_rad)
ax1.semilogx(freq, mag, lw=1.5)
ax1.set_ylabel("|Vout| [dB]"); ax1.grid(True, which="both", ls=":", alpha=0.4)
ax1.set_title("Pre-layout AC analysis - ota_5t (GF180MCU 3.3V)")
ax2.semilogx(freq, phase_deg, lw=1.5, color="tab:purple")
ax2.set_xlabel("Frequency [Hz]"); ax2.set_ylabel("Phase [°]"); ax2.grid(True, which="both", ls=":", alpha=0.4)
fig.tight_layout()
fig.savefig(f"{WD}/pre_ac.png", dpi=130)
plt.close(fig)
print(f"Saved {WD}/pre_ac.png  | flat gain ≈ {mag[0]:.2f} dB at {freq[0]:.1f} Hz")

# ---------- Pre-layout DC ----------
dc = parse_dat(f"{WD}/pre_dc.dat")
vp = dc["sweep"]            # Vin_p differential (V, range -50m..+50m)
vout = dc["c1"]             # v(out) real
fig, ax = plt.subplots(figsize=(9,4))
ax.plot(vp*1e3, vout, lw=1.5)
ax.set_xlabel("Differential input  V(+)-V(-)  [mV]")
ax.set_ylabel("Vout [V]")
ax.set_title("Pre-layout DC transfer - ota_5t")
ax.grid(True, ls=":", alpha=0.5)
fig.tight_layout()
fig.savefig(f"{WD}/pre_dc.png", dpi=130)
plt.close(fig)
# DC small-signal gain
i0 = np.argmin(np.abs(vp-0))
slope_per_mv = (vout[i0+3]-vout[i0-3])/(vp[i0+3]-vp[i0-3])  # V/V
print(f"Saved {WD}/pre_dc.png  | DC gain ≈ {20*np.log10(abs(slope_per_mv)):.2f} dB at Vout={vout[i0]:.4f}V")

# ---------- Pre-layout TRAN ----------
tran = parse_dat(f"{WD}/pre_tran.dat")
t = tran["sweep"]
vout_t = tran["c1"]
vin_t  = tran["c3"] * 1e3  # mV
fig, ax = plt.subplots(figsize=(9,4))
ax.plot(t*1e6, vout_t, lw=1.5, label="Vout")
ax.plot(t*1e6, vin_t,  lw=1.0, ls="--", label="Vin (diff, mV)")
ax.set_xlabel("Time [µs]"); ax.set_ylabel("Voltage [V]")
ax.set_title("Pre-layout TRAN response - ota_5t (1mV pulse, open-loop)")
ax.legend(); ax.grid(True, ls=":", alpha=0.5)
fig.tight_layout()
fig.savefig(f"{WD}/pre_tran.png", dpi=130)
plt.close(fig)
dv = vout_t.max() - vout_t.min()
print(f"Saved {WD}/pre_tran.png | output swing = {dv*1e3:.2f} mV")

print("DONE")
