Halo Mas Jabir, ada beberapa update yang perlu disampaikan:

1. **GitHub & PR**: Update di GitHub sudah diterima dan Pull Request dari Mas Jabir sudah saya merge ke `main`. PR #2 (OpenCode foundation + AI experiment audit) sudah terintegrasi. Terima kasih!

2. **Fitur Slash Command**: Mohon bantuannya untuk menambahkan fitur slash (`/`) pada **skills/tools** di OpenCode. Saya sudah membuat dua command baru:
   - `/mbg-full-automate` — alur desain otomatis penuh
   - `/mbg-partial-automate` — alur desain semi-otomatis dengan konfirmasi user

---

## Detail Alur Desain

### Pilihan Mode
User dapat memilih antara `/mbg-full-automate` atau `/mbg-partial-automate`.

---

### 1. Full Automate (`/mbg-full-automate`)

Alur otomatis penuh dari spesifikasi hingga tapeout:

| Step | Action | Detail |
|------|--------|--------|
| **1. Input User** | Tanya user | Desain apa dan spesifikasi apa yang diinginkan? |
| **2. Research** | Riset mendalam | Riset topology, sizing, dan trade-off berdasarkan design request user |
| **3. Konfirmasi** | Konfirmasi user | Tampilkan hasil riset, tanya apakah desain sudah OK |
| **4. Finetuning** | Simulasi ngspice | AI melakukan verifikasi simulasi dan finetuning sizing MOSFET |
| **5. Konversi & LVS** | SPICE → GDS | Konversi ke layout. Jika LVS mismatch, perbaiki arsitektur spice agar lebih sederhana dan LVS-friendly |
| **6. PEX & Matching** | Post-layout | Bandingkan pre-simulation vs post-simulation. Jika terlalu jauh, finetuning sizing MOSFET sampai mendekati spesifikasi |
| **7. Selesai** | Done | Layout siap untuk tapeout |

---

### 2. Partial Automate (`/mbg-partial-automate`)

Alur semi-otomatis — setiap step membutuhkan ide atau konfirmasi user:

| Step | Action | Detail |
|------|--------|--------|
| **1. Input User** | Tanya user | Desain dan spesifikasi |
| **2. Research** | Riset + konfirmasi | AI riset → tampilkan ke user → user beri masukan |
| **3. Spec-to-Netlist** | Generate + review | AI generate netlist → user review dan edit jika perlu |
| **4. Pre-Simulation** | Simulasi + review | AI jalankan ngspice → user review hasil |
| **5. Layout** | Place/Route + review | AI generate layout → user review dan beri arahan |
| **6. DRC/LVS** | Verifikasi | AI jalankan DRC/LVS → user review error |
| **7. PEX** | Post-sim | AI jalankan PEX → user bandingkan hasil |
| **8. Tapeout** | Final | User konfirmasi final sebelum tapeout |
