import heapq

class MultiPinRouter3D:
    def __init__(self, pr_boundary_coords, grid_resolution=0.1, total_layers=5):
        self.resolution = grid_resolution
        self.layers = total_layers
        self.min_x, self.min_y, self.max_x, self.max_y = pr_boundary_coords
        
        width = self.max_x - self.min_x
        height = self.max_y - self.min_y
        
        self.max_cols = int(round(width / self.resolution)) + 1
        self.max_rows = int(round(height / self.resolution)) + 1
        
        self.obstacles = set()
        print(f"[INIT] Multi-Pin Router Siap! Matriks: {self.max_cols}x{self.max_rows}")

    def physical_to_grid(self, x_um, y_um, layer):
        col = int(round((x_um - self.min_x) / self.resolution))
        row = int(round((y_um - self.min_y) / self.resolution))
        return (layer, row, col)

    def grid_to_physical(self, layer, row, col):
        x_um = round((col * self.resolution) + self.min_x, 3)
        y_um = round((row * self.resolution) + self.min_y, 3)
        return (layer, y_um, x_um)

    # ==========================================================
    # HELPER: MENGURAI GARIS MENJADI TITIK GRID PENUH
    # ==========================================================
    def _expand_path_to_grids(self, path_corners):
        """Mengurai titik sudut menjadi deretan grid lurus tanpa celah."""
        full_grids = set()
        for i in range(len(path_corners)-1):
            l1, r1, c1 = path_corners[i]
            l2, r2, c2 = path_corners[i+1]
            
            if l1 == l2: # Garis Lurus Horizontal/Vertikal
                for r in range(min(r1, r2), max(r1, r2) + 1):
                    for c in range(min(c1, c2), max(c1, c2) + 1):
                        full_grids.add((l1, r, c))
            else: # Via (Naik/Turun)
                full_grids.add((l1, r1, c1))
                full_grids.add((l2, r2, c2))
        return full_grids

    # ==========================================================
    # A* MULTI-TARGET RAY-CASTING
    # ==========================================================
    def _route_astar_multitarget(self, start_grid, target_grids, all_pins_grid):
        # Jika titik mulai sudah ada di dalam batang rute, tidak perlu ditarik lagi
        if start_grid in target_grids:
            return [start_grid]

        # Bounding box dari target_grids untuk mempercepat fungsi pencari arah (Heuristik)
        min_l = min(t[0] for t in target_grids)
        max_l = max(t[0] for t in target_grids)
        min_r = min(t[1] for t in target_grids)
        max_r = max(t[1] for t in target_grids)
        min_c = min(t[2] for t in target_grids)
        max_c = max(t[2] for t in target_grids)

        def heuristic(l, r, c):
            return (max(0, min_l - l, l - max_l) * 5 + 
                    max(0, min_r - r, r - max_r) + 
                    max(0, min_c - c, c - max_c))

        pq = [(heuristic(*start_grid), 0, start_grid[0], start_grid[1], start_grid[2])]
        g_score = {start_grid: 0}
        parent = {start_grid: None}

        moves = [
            (0, 0, -1, True, False, False), (0, 0, 1, True, False, False),
            (0, -1, 0, False, True, False), (0, 1, 0, False, True, False),
            (-1, 0, 0, False, False, True), (1, 0, 0, False, False, True)
        ]

        while pq:
            curr_f, curr_g, curr_l, curr_r, curr_c = heapq.heappop(pq)
            
            # CEK TARGET: Apakah meluncur menabrak batang utama koneksi kita sendiri?
            if (curr_l, curr_r, curr_c) in target_grids:
                path = []
                curr = (curr_l, curr_r, curr_c)
                while curr is not None:
                    path.append(curr)
                    curr = parent[curr]
                path.reverse()
                return path

            if curr_g > g_score.get((curr_l, curr_r, curr_c), float('inf')): continue

            is_even_layer = (curr_l % 2 == 0)

            for dl, dr, dc, is_horiz, is_vert, is_via in moves:
                if is_via:
                    nl = curr_l + dl
                    # Boleh pasang via asalkan tidak nabrak obstacle OR via itu bagian dari target
                    if 0 <= nl < self.layers:
                        hit_target = (nl, curr_r, curr_c) in target_grids
                        hit_obs = not hit_target and (nl, curr_r, curr_c) in self.obstacles
                        
                        if not hit_obs:
                            tentative_g = curr_g + 5
                            if tentative_g < g_score.get((nl, curr_r, curr_c), float('inf')):
                                g_score[(nl, curr_r, curr_c)] = tentative_g
                                parent[(nl, curr_r, curr_c)] = (curr_l, curr_r, curr_c)
                                heapq.heappush(pq, (tentative_g + heuristic(nl, curr_r, curr_c), tentative_g, nl, curr_r, curr_c))
                else:
                    nr, nc = curr_r, curr_c
                    langkah = 0
                    
                    while True:
                        next_r, next_c = nr + dr, nc + dc
                        next_node = (curr_l, next_r, next_c)
                        
                        out_bounds = not (0 <= next_r < self.max_rows and 0 <= next_c < self.max_cols)
                        hit_target = next_node in target_grids
                        
                        # Obstacle valid jika itu BUKAN target koneksi kita
                        hit_obs = not hit_target and next_node in self.obstacles
                        
                        if out_bounds or hit_obs or hit_target:
                            if hit_target:
                                # Jika ketemu trunk, lari lurus tepat masuk ke trunk tersebut
                                langkah += 1
                                denda = 20 if (is_even_layer and is_vert) or (not is_even_layer and is_horiz) else 1
                                tentative_g = curr_g + (langkah * denda)
                                if tentative_g < g_score.get(next_node, float('inf')):
                                    g_score[next_node] = tentative_g
                                    parent[next_node] = (curr_l, curr_r, curr_c)
                                    heapq.heappush(pq, (tentative_g + heuristic(*next_node), tentative_g, *next_node))
                            else:
                                # Berhenti di depan rintangan (obstacle)
                                if langkah > 0:
                                    stop_node = (curr_l, nr, nc)
                                    denda = 20 if (is_even_layer and is_vert) or (not is_even_layer and is_horiz) else 1
                                    tentative_g = curr_g + (langkah * denda)
                                    if tentative_g < g_score.get(stop_node, float('inf')):
                                        g_score[stop_node] = tentative_g
                                        parent[stop_node] = (curr_l, curr_r, curr_c)
                                        heapq.heappush(pq, (tentative_g + heuristic(*stop_node), tentative_g, *stop_node))
                            break
                        
                        nr, nc = next_r, next_c
                        langkah += 1
                        
                        # Cek Penyelarasan (Alignment): Ciptakan waypoint jika sinar sejajar dengan salah satu pin
                        aligned_with_pin = any((nr == p[1] and is_vert) or (nc == p[2] and is_horiz) for p in all_pins_grid)
                        if aligned_with_pin:
                            drop_node = (curr_l, nr, nc)
                            denda = 20 if (is_even_layer and is_vert) or (not is_even_layer and is_horiz) else 1
                            tentative_g = curr_g + (langkah * denda)
                            if tentative_g < g_score.get(drop_node, float('inf')):
                                g_score[drop_node] = tentative_g
                                parent[drop_node] = (curr_l, curr_r, curr_c)
                                heapq.heappush(pq, (tentative_g + heuristic(*drop_node), tentative_g, *drop_node))

        return None

    def _convert_path_to_matrices(self, path_phys):
        matriks = []
        for i in range(len(path_phys)-1):
            l1, y1, x1 = path_phys[i]
            l2, y2, x2 = path_phys[i+1]
            
            arah = ""
            if l2 > l1: arah = "Up"
            elif l2 < l1: arah = "Down"
            elif y2 > y1: arah = "North"
            elif y2 < y1: arah = "South"
            elif x2 > x1: arah = "East"
            elif x2 < x1: arah = "West"
            
            matriks.append([(x1, y1), (x2, y2), l1+1, l2+1, arah])
        return matriks

    # ==========================================================
    # FUNGSI UTAMA: SEQUENTIAL MULTI-PIN
    # ==========================================================
    def route_sequential(self, daftar_net):
        hasil_semua_rute = {}
        
        for net_name, list_pins_phys in daftar_net:
            print(f"--- Memproses {net_name} ({len(list_pins_phys)} Pin) ---")
            
            pins_grid = [self.physical_to_grid(*p) for p in list_pins_phys]
            
            # Inisialisasi 'Trunk' dengan Pin pertama
            trunk_grids = set([pins_grid[0]])
            self.obstacles.add(pins_grid[0])
            
            net_vectors = []
            sukses_semua = True
            
            # Tarik rute dari pin sisa (Pin 2, 3, dst) menuju Trunk yang terus membesar
            for i in range(1, len(pins_grid)):
                start_pin = pins_grid[i]
                
                path_corners = self._route_astar_multitarget(start_pin, trunk_grids, pins_grid)
                
                if path_corners:
                    # 1. Urai jalan menjadi grid penuh dan tambahkan ke memori Trunk
                    new_trunk_segment = self._expand_path_to_grids(path_corners)
                    trunk_grids.update(new_trunk_segment)
                    
                    # 2. Tambahkan ke memori rintangan Global
                    self.obstacles.update(new_trunk_segment)
                    
                    # 3. Ubah menjadi Vektor dan tambahkan ke koleksi net ini
                    path_phys = [self.grid_to_physical(*pt) for pt in path_corners]
                    net_vectors.extend(self._convert_path_to_matrices(path_phys))
                else:
                    print(f"  [GAGAL] Pin ke-{i+1} terblokir.")
                    sukses_semua = False
                    break
            
            if sukses_semua:
                hasil_semua_rute[net_name] = net_vectors
                print(f"  [SUCCESS] {net_name} selesai dibuat dengan {len(net_vectors)} segmen garis.")
            else:
                hasil_semua_rute[net_name] = None
                
        return hasil_semua_rute

# ==========================================
# UJI COBA KONEKSI T-JUNCTION (MULTI-PIN)
# ==========================================
if __name__ == "__main__":
    batas = (-20.0, -20.0, 20.0, 20.0)
    router = MultiPinRouter3D(pr_boundary_coords=batas, grid_resolution=0.1)

    daftar_koneksi = [
        # NET_VDD menyambung TIGA pin sekaligus! (Sistem akan membentuk huruf T otomatis)
        # Pin 1: (Kiri), Pin 2: (Kanan), Pin 3: (Bawah Tengah)
        ("NET_VDD_GLOBAL", [
            (10.0, 15.0, 0),  # Pin 1 (Start Trunk)
            (20.0, 15.0, 0),  # Pin 2 (Target 1)
            (15.0,  5.0, 0)   # Pin 3 (Target 2)
        ]),
        
        # NET CLOCK biasa lewat di tengah, harus lari menghindari "Batang" T-Junction VDD
        ("NET_CLOCK", [
            (15.0,  2.0, 0),  # Mulai di bawah Pin 3 VDD
            (15.0, 18.0, 0)   # Tembus jauh ke atas melewati VDD
        ])
    ]

    semua_matriks = router.route_sequential(daftar_koneksi)

    print("\n=== OUTPUT MATRIKS MULTI-PIN ===")
    for net_nama, matriks in semua_matriks.items():
        print(f"\nRute: {net_nama}")
        if matriks:
            for baris in matriks:
                print(f"  {baris}")