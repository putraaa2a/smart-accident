# 📍 DOKUMENTASI TEKNIS: SMART ACCIDENT SYSTEM

## Mapping Kecelakaan ke Segmen Jalan & Visualisasi Peta Interaktif

---

## 📋 DAFTAR ISI

1. [Bagian 1: Membuat Mark Jalan pada Peta & Membagi Segmen Per Titik](#bagian-1)
2. [Bagian 2: Mencocokkan Titik Kecelakaan dengan Segmen Jalan](#bagian-2)
3. [Bagian 3: Visualisasi pada Peta Interaktif](#bagian-3)

---

## <a name="bagian-1"></a>BAGIAN 1: MEMBUAT MARK JALAN PADA PETA & MEMBAGI SEGMEN PER TITIK

### 1.1 Struktur Data Model

#### Model RuasJalan (Jalan Utama)

```python
class RuasJalan(models.Model):
    """Model untuk data ruas jalan"""

    id = models.AutoField(primary_key=True)
    nama_ruas = models.CharField(max_length=50)              # Nama jalan
    jenis_jalan = models.CharField(max_length=20)            # Tol, Arteri, Kolektor, dll
    wilayah = models.CharField(max_length=40)                # Area wilayah
    panjang_km = models.DecimalField(max_digits=10, decimal_places=3)  # Total panjang

    # Koordinat Titik Awal Ruas Jalan
    lat_awal = models.DecimalField(max_digits=25, decimal_places=20)
    lon_awal = models.DecimalField(max_digits=25, decimal_places=20)

    # Koordinat Titik Akhir Ruas Jalan
    lat_akhir = models.DecimalField(max_digits=25, decimal_places=20)
    lon_akhir = models.DecimalField(max_digits=25, decimal_places=20)

    # Geometry dalam format GeoJSON LineString
    geometry = models.TextField(
        help_text="GeoJSON LineString untuk seluruh ruas jalan"
    )
    polres = models.ForeignKey('Polres', on_delete=models.SET_NULL, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

**Penjelasan:**

- **geometry**: Menyimpan koordinat seluruh jalur jalan dalam format GeoJSON LineString
- **lat_awal/lon_awal**: Koordinat penanda merah di awal ruas jalan
- **lat_akhir/lon_akhir**: Koordinat penanda merah di akhir ruas jalan

---

#### Model SegmenJalan (Pembagian Segmen)

```python
class SegmenJalan(models.Model):
    """Model untuk data segmen jalan (pembagian dari ruas jalan)"""

    id = models.AutoField(primary_key=True)
    ruas_jalan = models.ForeignKey(RuasJalan, on_delete=models.CASCADE)

    # KM Awal dan Akhir Segmen (misal: Km 0-5, Km 5-10, dst)
    km_awal = models.DecimalField(max_digits=10, decimal_places=3)
    km_akhir = models.DecimalField(max_digits=10, decimal_places=3)
    panjang_segmen = models.DecimalField(max_digits=10, decimal_places=3)

    # Koordinat Titik Awal Segmen (penanda biru kecil)
    lat_awal = models.DecimalField(max_digits=25, decimal_places=20, null=True)
    lon_awal = models.DecimalField(max_digits=25, decimal_places=20, null=True)

    # Koordinat Titik Akhir Segmen (penanda biru kecil)
    lat_akhir = models.DecimalField(max_digits=25, decimal_places=20, null=True)
    lon_akhir = models.DecimalField(max_digits=25, decimal_places=20, null=True)

    titik_awal = models.CharField(max_length=30, null=True, help_text="Label: Titik 1")
    titik_akhir = models.CharField(max_length=30, null=True, help_text="Label: Titik 2")

    # Geometry segmen jalan
    geometry = models.TextField(null=True, help_text="GeoJSON LineString untuk segmen")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

---

### 1.2 Proses Pembagian Segmen (Segmentasi Ruas Jalan)

Ketika ruas jalan ditambahkan, sistem otomatis membagi menjadi segmen-segmen. Ada 2 mode:

#### **Mode 1: Manual (User Menentukan Titik Pembagi)**

User dapat mengklik pada peta untuk menentukan titik-titik pembagi segmen. Data dikirim ke backend dalam format:

```javascript
// Data dari frontend (map click)
const manualSplits = [
  { km: 0.0, lat: -7.6298, lon: 111.5239 }, // Titik awal
  { km: 2.5, lat: -7.635, lon: 111.54 }, // Titik 1 (hasil klik)
  { km: 5.0, lat: -7.64, lon: 111.555 }, // Titik 2 (hasil klik)
  { km: 8.523, lat: -7.65, lon: 111.57 }, // Titik akhir
];
```

#### **Mode 2: Otomatis (Menggunakan Simpang Jalan dari API)**

Sistem menggunakan Overpass API untuk menemukan persimpangan/titik percabangan jalan.

---

### 1.3 Kode Pembagian Segmen (Backend)

```python
def generate_segmen(self):
    """
    Generate segmen jalan otomatis berdasarkan titik klik manual
    atau simpang jalan dari Overpass API

    ALUR KERJA:
    1. Hapus segmen lama
    2. Parse geometry dari JSON (bisa LineString atau MultiLineString)
    3. Hitung jarak kumulatif setiap koordinat menggunakan Geodesic
    4. Tentukan titik-titik pembagi (splits) - Manual atau Otomatis
    5. Hitung koordinat untuk setiap split point
    6. Buat record SegmenJalan di database
    """

    # 1. Hapus segmen lama jika ada
    SegmenJalan.objects.filter(ruas_jalan=self).delete()

    if not self.geometry:
        print(f"Skipping generate_segmen for {self.nama_ruas}: No geometry.")
        return

    # 2. Parse geometry (bisa berupa GeoJSON Feature atau raw geometry)
    try:
        geom_data = json.loads(self.geometry)
        if geom_data.get('type') == 'Feature':
            properties = geom_data.get('properties', {})
            manual_splits = properties.get('splits', [])
            segment_geometries = properties.get('segment_geometries', [])
            segment_info = properties.get('segment_info', [])
            geom_obj = geom_data.get('geometry', {})
        else:
            manual_splits = []
            segment_geometries = []
            segment_info = []
            geom_obj = geom_data

        geom_type = geom_obj.get('type')
        raw_coords = geom_obj.get('coordinates', [])

        # Konversi MultiLineString ke LineString
        if geom_type == 'LineString':
            coords = raw_coords
        elif geom_type == 'MultiLineString':
            coords = [pt for line in raw_coords for pt in line]
        else:
            coords = raw_coords

        if not coords or not isinstance(coords[0], list):
            print(f"Skipping generate_segmen for {self.nama_ruas}: Invalid coordinates format.")
            return
    except Exception as e:
        print(f"Error parsing geometry: {e}")
        return

    # 3. Hitung jarak kumulatif untuk setiap koordinat menggunakan Geodesic
    source_coords = coords
    cumulative_distances = [0.0]
    total_dist = 0.0

    for i in range(len(source_coords) - 1):
        p1 = source_coords[i]  # [lon, lat]
        p2 = source_coords[i+1]  # [lon, lat]
        try:
            # geodesic() menghitung jarak great-circle dengan akurat
            d = geodesic((p1[1], p1[0]), (p2[1], p2[0])).kilometers
            total_dist += d
            cumulative_distances.append(total_dist)
        except Exception as e:
            print(f"Error calculating geodesic distance: {e}")
            cumulative_distances.append(total_dist)

    # 4. Tentukan titik-titik pembagi (splits)
    final_points = []  # List of {km, lat, lon}

    if manual_splits:
        # ✅ MODE MANUAL: User sudah klik titik-titik di peta
        print(f"Using manual splits for {self.nama_ruas}: {manual_splits}")

        for s in manual_splits:
            if isinstance(s, dict):
                final_points.append({
                    'km': float(s.get('km', 0)),
                    'lat': s.get('lat'),
                    'lon': s.get('lon')
                })

        # Sortir berdasarkan KM dan hapus duplikat
        final_points.sort(key=lambda x: x['km'])

        # Jika titik pertama bukan 0, tambahkan titik awal
        if not any(p['km'] == 0 for p in final_points):
            final_points.insert(0, {
                'km': 0.0,
                'lat': coords[0][1],
                'lon': coords[0][0]
            })
    else:
        # ✅ MODE OTOMATIS: Gunakan Overpass API untuk mencari persimpangan
        print(f"No manual splits, using Overpass API for {self.nama_ruas}")

        # [Kode Overpass API dipotong untuk singkat - mencari junction points]
        auto_kms = [0.0]  # Selalu mulai dari 0
        # ... Overpass API logic ...

    # 5. Buat SegmenJalan di database
    for i in range(len(final_points) - 1):
        km_start = final_points[i]['km']
        km_end = final_points[i+1]['km']
        panjang = km_end - km_start

        # Ambil koordinat dari split point
        lat_awal = final_points[i]['lat']
        lon_awal = final_points[i]['lon']
        lat_akhir = final_points[i+1]['lat']
        lon_akhir = final_points[i+1]['lon']

        # Buat segment geometry
        seg_geometry = self._get_segment_geometry(km_start, km_end)

        # Create database record
        SegmenJalan.objects.create(
            ruas_jalan=self,
            km_awal=km_start,
            km_akhir=km_end,
            panjang_segmen=panjang,
            lat_awal=lat_awal,
            lon_awal=lon_awal,
            lat_akhir=lat_akhir,
            lon_akhir=lon_akhir,
            titik_awal=f"Titik {i+1}",
            titik_akhir=f"Titik {i+2}",
            nama_segmen=f"Segmen {i+1}",
            geometry=json.dumps(seg_geometry) if seg_geometry else None
        )

        print(f"✓ Created Segmen {i+1}: Km {km_start}-{km_end}")

    print(f"Successfully generated {len(final_points) - 1} segments for {self.nama_ruas}.")
```

---

### 1.4 Fungsi Pembantu: Hitung Geometry Segmen

```python
def _get_segment_geometry(self, km_start, km_end):
    """
    FUNGSI: Ekstrak koordinat dari ruas jalan untuk rentang KM tertentu

    INPUT:
    - km_start: KM awal segmen (misal 0)
    - km_end: KM akhir segmen (misal 5)

    OUTPUT:
    - GeoJSON geometry untuk segmen (LineString)

    CARA KERJA:
    1. Iterate semua koordinat ruas jalan
    2. Hitung jarak kumulatif (dari titik awal hingga setiap koordinat)
    3. Jika jarak ada di antara km_start dan km_end, masukkan ke segment_coords
    4. Return sebagai LineString GeoJSON
    """

    try:
        geom_data = json.loads(self.geometry)
        if geom_data.get('type') == 'Feature':
            geom_obj = geom_data.get('geometry', {})
        else:
            geom_obj = geom_data

        coords = geom_obj.get('coordinates', [])
        if not coords or isinstance(coords[0], (int, float)):
            return None

        # Hitung jarak kumulatif
        cumulative_distances = [0.0]
        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i+1]
            d = geodesic((p1[1], p1[0]), (p2[1], p2[0])).kilometers
            cumulative_distances.append(cumulative_distances[-1] + d)

        # Ekstrak koordinat yang ada dalam rentang KM
        segment_coords = []
        for i, coord in enumerate(coords):
            dist = cumulative_distances[i]
            if km_start <= dist <= km_end:
                if not segment_coords:
                    segment_coords.append(coord)
                elif coord != segment_coords[-1]:
                    segment_coords.append(coord)

        if segment_coords and len(segment_coords) > 1:
            return {
                'type': 'LineString',
                'coordinates': segment_coords
            }
        else:
            # Fallback: Hanya awal dan akhir
            return {
                'type': 'LineString',
                'coordinates': [
                    [float(self.lon_awal), float(self.lat_awal)],
                    [float(self.lon_akhir), float(self.lat_akhir)]
                ]
            }
    except Exception as e:
        print(f"Error in _get_segment_geometry: {e}")
        return None
```

**Penjelasan Algoritma:**

- Menggunakan **geodesic distance** (Haversine formula) untuk akurasi geografis
- Iterasi setiap koordinat dan hitung jarak dari titik awal
- Pilih koordinat yang berada di antara km_start dan km_end
- Format sebagai GeoJSON LineString untuk rendering di peta

---

## <a name="bagian-2"></a>BAGIAN 2: MENCOCOKKAN TITIK KECELAKAAN DENGAN SEGMEN JALAN

### 2.1 Alur Pencocokkan Otomatis

Ketika data kecelakaan disimpan ke database, sistem otomatis mencocokan koordinat kecelakaan (latitude/longitude) dengan segmen jalan terdekat.

```python
class Kecelakaan(models.Model):
    """Model untuk data kecelakaan"""

    id = models.AutoField(primary_key=True)
    tanggal = models.DateField()
    waktu = models.TimeField()

    # Koordinat lokasi kecelakaan
    latitude = models.DecimalField(max_digits=30, decimal_places=20)
    longitude = models.DecimalField(max_digits=30, decimal_places=20)

    # Segmen jalan hasil pencocokkan otomatis
    segmen_jalan = models.ForeignKey(
        SegmenJalan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Otomatis diassign ke segmen terdekat (threshold 50m) saat disimpan"
    )

    korban_meninggal = models.IntegerField(default=0)
    korban_luka_berat = models.IntegerField(default=0)
    korban_luka_ringan = models.IntegerField(default=0)
    kerugian_materi = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    desa = models.CharField(max_length=100)
    kecamatan = models.CharField(max_length=100)
    kabupaten_kota = models.CharField(max_length=100)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """Override save untuk otomatis pencocokkan segmen"""
        super().save(*args, **kwargs)

        # Otomatis assign segmen jalan terdekat jika kosong
        if self.latitude and self.longitude and not self.segmen_jalan:
            self.find_closest_segment()
            # Jika berhasil assign, simpan perubahan
            if self.segmen_jalan:
                super().save(update_fields=['segmen_jalan'])
```

---

### 2.2 Algoritma Pencocokkan (Perpendicular Distance)

```python
def find_closest_segment(self):
    """
    🎯 ALGORITMA PENCOCOKKAN UTAMA

    Temukan segmen jalan di mana titik kecelakaan berada TEPAT DI ANTARA
    titik awal dan titik akhir segmen. Menggunakan PROYEKSI PERPENDICULAR
    dari titik ke garis segmen untuk presisi maksimal.

    LANGKAH-LANGKAH:
    1. Cek apakah titik kecelakaan ada dalam bounding box segmen (quick check)
    2. Hitung jarak perpendicular dari titik ke garis segmen
    3. Jika jarak perpendicular <= tolerance (50m), ini adalah match
    4. Assign ke segmen dengan jarak perpendicular terkecil
    """

    import math

    accident_lat = float(self.latitude)
    accident_lon = float(self.longitude)

    # Tolerance untuk jarak perpendicular: ~50 meter
    tolerance_km = 0.050

    best_match = None
    smallest_distance = float('inf')

    # Iterasi semua segmen untuk cek titik
    for segmen in SegmenJalan.objects.select_related('ruas_jalan').all():
        if not (segmen.lat_awal and segmen.lon_awal and
                segmen.lat_akhir and segmen.lon_akhir):
            continue

        s_lat_awal = float(segmen.lat_awal)
        s_lon_awal = float(segmen.lon_awal)
        s_lat_akhir = float(segmen.lat_akhir)
        s_lon_akhir = float(segmen.lon_akhir)

        # ✅ STEP 1: Cek bounding box dulu (quick filter)
        # Buffer ~111 meter
        buffer = 0.001
        min_lat = min(s_lat_awal, s_lat_akhir) - buffer
        max_lat = max(s_lat_awal, s_lat_akhir) + buffer
        min_lon = min(s_lon_awal, s_lon_akhir) - buffer
        max_lon = max(s_lon_awal, s_lon_akhir) + buffer

        # Skip jika titik kecelakaan di luar bounding box
        if not (min_lat <= accident_lat <= max_lat and
                min_lon <= accident_lon <= max_lon):
            continue

        # ✅ STEP 2: Hitung jarak perpendicular dari titik ke garis segmen
        perp_distance = self._calculate_perpendicular_distance(
            accident_lat, accident_lon,
            s_lat_awal, s_lon_awal,
            s_lat_akhir, s_lon_akhir
        )

        # ✅ STEP 3: Jika jarak perpendicular <= tolerance, ini adalah match
        if perp_distance is not None and perp_distance <= tolerance_km:
            if perp_distance < smallest_distance:
                smallest_distance = perp_distance
                best_match = segmen

    # ✅ STEP 4: Assign ke segmen terbaik jika ada match
    if best_match:
        self.segmen_jalan = best_match
        print(f"✓ Kecelakaan {self.id} → Segmen '{best_match.nama_segmen}' "
              f"(jarak perp: {smallest_distance*1000:.1f}m)")
    else:
        print(f"⚠ Kecelakaan {self.id}: Tidak ada segmen yang sesuai "
              f"(tolerance: {tolerance_km*1000:.0f}m)")
```

---

### 2.3 Perhitungan Jarak Perpendicular (Core Algorithm)

```python
def _calculate_perpendicular_distance(self, lat, lon, lat1, lon1, lat2, lon2):
    """
    🔬 FUNGSI MATEMATIKA: Hitung jarak PERPENDICULAR dari titik ke garis

    PENJELASAN GEOMETRI:

    Garis Segmen Jalan (dari titik 1 ke titik 2):
    ────────────────────────────

    Titik Kecelakaan:
             ·
             |  ← jarak perpendicular
             |

    Algoritma:
    1. Konversi lat/lon ke radian (untuk perhitungan bola)
    2. Hitung angular distance dari titik awal ke titik kecelakaan
    3. Hitung bearing (sudut) dari titik awal ke titik akhir
    4. Hitung bearing dari titik awal ke titik kecelakaan
    5. Hitung cross-track distance (perpendicular distance)
    6. Hitung along-track distance (untuk cek apakah dalam rentang)
    7. Validasi proyeksi ada dalam rentang segmen

    INPUT: (Semua dalam latitude/longitude degrees)
    - (lat, lon) = Titik kecelakaan
    - (lat1, lon1) = Titik awal segmen
    - (lat2, lon2) = Titik akhir segmen

    OUTPUT:
    - Jarak dalam KM jika titik proyeksi ada dalam segmen
    - None jika titik proyeksi di luar rentang segmen
    """

    import math

    # ✅ STEP 1: Konversi ke radian
    lat = math.radians(lat)
    lon = math.radians(lon)
    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    R = 6371  # Radius bumi dalam KM

    # ✅ STEP 2: Hitung angular distance dari titik awal (1) ke kecelakaan
    dLat = lat - lat1
    dLon = lon - lon1
    a = math.sin(dLat/2)**2 + math.cos(lat1) * math.cos(lat) * math.sin(dLon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    d13 = R * c  # Angular distance dalam KM

    # ✅ STEP 3: Hitung bearing dari titik 1 ke titik 2 (segmen direction)
    dLon12 = lon2 - lon1
    y = math.sin(dLon12) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dLon12)
    theta12 = math.atan2(y, x)  # Bearing dalam radian

    # ✅ STEP 4: Hitung bearing dari titik 1 ke kecelakaan
    dLon13 = lon - lon1
    y13 = math.sin(dLon13) * math.cos(lat)
    x13 = math.cos(lat1) * math.sin(lat) - math.sin(lat1) * math.cos(lat) * math.cos(dLon13)
    theta13 = math.atan2(y13, x13)  # Bearing dalam radian

    # ✅ STEP 5: Hitung CROSS-TRACK distance (perpendicular distance)
    # Ini adalah jarak terpendek dari titik ke garis
    dXt = math.asin(math.sin(d13/R) * math.sin(theta13 - theta12))
    cross_track_distance_km = abs(dXt * R)

    # ✅ STEP 6: Hitung ALONG-TRACK distance
    # Ini menentukan di mana proyeksi berada di garis (0 = awal, max = akhir)
    try:
        dAt = math.acos(max(-1, min(1, math.cos(d13/R) / abs(math.cos(dXt)))))
    except:
        dAt = 0

    # ✅ STEP 7: Hitung jarak dari titik awal ke titik akhir
    dLat12 = lat2 - lat1
    dLon12_calc = lon2 - lon1
    a12 = math.sin(dLat12/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dLon12_calc/2)**2
    c12 = 2 * math.asin(math.sqrt(a12))
    d12 = R * c12  # Panjang segmen dalam KM

    # ✅ STEP 8: Validasi proyeksi ada dalam rentang segmen
    # -0.05 km (5 km di awal) hingga d12 + 0.05 km (5 km di akhir)
    if -0.05 <= dAt <= (d12 + 0.05):
        # ✅ Titik proyeksi ada dalam rentang segmen
        return cross_track_distance_km
    else:
        # ❌ Titik proyeksi di luar rentang segmen
        return None
```

---

### 2.4 Ilustrasi Algoritma Pencocokkan

```
SKENARIO 1: Kecelakaan Cocok dengan Segmen
═════════════════════════════════════════════

Segmen Jalan:
Point A (Km 0) ─────────────────── Point B (Km 5)

Titik Kecelakaan:
                    ·  ← Jarak perp = 30 meter (< 50m) ✅ MATCH
                    |
Point A ─────·──────────────── Point B

Hasil: Assign ke segmen ini


SKENARIO 2: Kecelakaan Terlalu Jauh
═════════════════════════════════════════════

Titik Kecelakaan:
                    ·  ← Jarak perp = 200 meter (> 50m) ❌ NO MATCH
                    |
                    | (terlalu jauh)
                    |
Point A ─────────────────────── Point B

Hasil: Tidak diassign ke segmen ini


SKENARIO 3: Proyeksi di Luar Rentang Segmen
═════════════════════════════════════════════

        ·  ← Titik kecelakaan
        |
        | Proyeksi di luar rentang
        |
Point A ─────────────────── Point B


Hasil: Tidak diassign (proyeksi di luar segmen)
```

---

## <a name="bagian-3"></a>BAGIAN 3: VISUALISASI PADA PETA INTERAKTIF

### 3.1 API Backend: Kirim GeoJSON ke Frontend

```python
@api_view(['GET'])
def api_segmen_geojson(request):
    """
    📡 API untuk mendapatkan GeoJSON segmen jalan dengan Z-Score

    ALUR:
    1. Ambil tahun dari query parameter
    2. Hitung Z-Score untuk tahun tersebut (jika belum ada)
    3. Untuk setiap segmen:
       - Ambil geometry (LineString)
       - Hitung jumlah kecelakaan di segmen tersebut
       - Tentukan kategori berdasarkan Z-Score (Aman, Rendah, Sedang, Tinggi, Sangat Tinggi)
       - Tentukan warna marker berdasarkan kategori
    4. Return sebagai GeoJSON FeatureCollection
    """

    tahun_raw = request.GET.get('tahun')

    # Parse tahun parameter
    if not tahun_raw or tahun_raw == 'None' or tahun_raw == '0':
        tahun = 0  # Semua tahun
    else:
        try:
            tahun = int(tahun_raw)
        except (ValueError, TypeError):
            tahun = 0

    print(f"\n📍 API: api_segmen_geojson called for tahun={tahun}")

    # Ensure Z-Score calculation exists for this year
    if not AnalisisZScore.objects.filter(tahun=tahun).exists():
        try:
            AnalisisZScore.calculate_zscore(tahun)
            print(f"✓ Auto-calculated Z-Score for {tahun}")
        except Exception as e:
            print(f"⚠ Could not auto-calculate Z-Score: {e}")

    segmen_list = SegmenJalan.objects.select_related('ruas_jalan').all()
    features = []

    for segmen in segmen_list:
        # ✅ STEP 1: Hitung jumlah kecelakaan di segmen
        if tahun == 0:
            accident_count = KecelakaanPreprosesing.objects.filter(
                segmen_jalan=segmen
            ).count()
        else:
            accident_count = KecelakaanPreprosesing.objects.filter(
                segmen_jalan=segmen,
                tanggal__year=tahun
            ).count()

        # ✅ STEP 2: Tentukan kategori berdasarkan Z-Score
        # PENTING: Jika tidak ada kecelakaan, kategori selalu "AMAN" (biru)
        if accident_count == 0:
            kategori = 'aman'
            zscore = -2.0
            color = '#1976d2'  # Biru
        else:
            # Ada kecelakaan - ambil dari Z-Score analysis
            try:
                analisis = AnalisisZScore.objects.get(
                    segmen_jalan=segmen,
                    tahun=tahun
                )
                kategori = analisis.kategori
                zscore = float(analisis.nilai_zscore)
                color = analisis.get_kategori_display_color()
            except AnalisisZScore.DoesNotExist:
                kategori = 'unknown'
                zscore = 0
                color = '#999999'

        # ✅ STEP 3: Ambil atau generate geometry
        geometry = None
        if segmen.geometry:
            try:
                parsed_geom = json.loads(segmen.geometry)
                # Convert MultiLineString to LineString untuk rendering
                if parsed_geom.get('type') == 'MultiLineString':
                    coords = []
                    for line in parsed_geom.get('coordinates', []):
                        coords.extend(line)
                    geometry = {'type': 'LineString', 'coordinates': coords}
                else:
                    geometry = parsed_geom
            except Exception as e:
                print(f"⚠ Error parsing geometry for segmen {segmen.id}: {e}")
                geometry = None

        # Fallback: Generate dari lat/lon
        if not geometry:
            if segmen.lat_awal and segmen.lon_awal and \
               segmen.lat_akhir and segmen.lon_akhir:
                geometry = {
                    'type': 'LineString',
                    'coordinates': [
                        [float(segmen.lon_awal), float(segmen.lat_awal)],
                        [float(segmen.lon_akhir), float(segmen.lat_akhir)]
                    ]
                }

        # ✅ STEP 4: Buat GeoJSON Feature
        feature = {
            'type': 'Feature',
            'id': segmen.id,
            'geometry': geometry,
            'properties': {
                'id': segmen.id,
                'nama_segmen': segmen.nama_segmen or f"Segmen {segmen.km_awal}-{segmen.km_akhir} km",
                'ruas_jalan': segmen.ruas_jalan.nama_ruas,
                'km_awal': float(segmen.km_awal),
                'km_akhir': float(segmen.km_akhir),
                'kategori': kategori,
                'zscore': zscore,
                'color': color,
                'accident_count': accident_count,
                'lat_awal': float(segmen.lat_awal) if segmen.lat_awal else None,
                'lon_awal': float(segmen.lon_awal) if segmen.lon_awal else None,
                'lat_akhir': float(segmen.lat_akhir) if segmen.lat_akhir else None,
                'lon_akhir': float(segmen.lon_akhir) if segmen.lon_akhir else None,
            }
        }
        features.append(feature)

    return Response({
        'type': 'FeatureCollection',
        'features': features
    })
```

---

### 3.2 Frontend: Render GeoJSON pada Peta Leaflet

```javascript
// Initialize Map dengan Leaflet
function initMap() {
  // 📍 Buat map dengan center di Madiun
  map = L.map("mapContainer").setView([-7.6298, 111.5239], 13);

  // 🗺️ Add tile layer (OpenStreetMap atau MapTiler)
  L.tileLayer(
    "https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}@2x.png?key=YOUR_KEY",
    {
      attribution: "© MapTiler © OpenStreetMap contributors",
      maxZoom: 19,
      tileSize: 512,
      zoomOffset: -1,
    },
  ).addTo(map);

  // Load data
  loadSegmenData();
}

// ✅ Load GeoJSON dari API dan render di peta
function loadSegmenData() {
  const url = `/api/segmen/geojson/?tahun=${tahun}`;
  console.log("📡 Loading segmen data from API:", url);

  axios
    .get(url)
    .then((response) => {
      const geojson = response.data;
      console.log(`✅ Loaded ${geojson.features.length} segments`);

      // Clear old layer jika ada
      if (segmenLayer) {
        map.removeLayer(segmenLayer);
      }

      // ✅ Create GeoJSON layer dengan styling
      segmenLayer = L.geoJSON(geojson, {
        style: function (feature) {
          // 🎨 Style garis berdasarkan kategori
          return {
            color: feature.properties.color,
            weight: 4,
            opacity: 0.8,
            dashArray: feature.properties.kategori === "aman" ? "5, 5" : "0",
          };
        },

        onEachFeature: function (feature, layer) {
          // 🔴 Add marker untuk awal dan akhir segmen

          // Marker awal (biru kecil)
          L.circleMarker(
            [feature.properties.lat_awal, feature.properties.lon_awal],
            {
              radius: 4,
              fillColor: "#1976d2",
              color: "#fff",
              weight: 2,
              opacity: 1,
              fillOpacity: 0.8,
            },
          ).addTo(map);

          // Marker akhir (biru kecil)
          L.circleMarker(
            [feature.properties.lat_akhir, feature.properties.lon_akhir],
            {
              radius: 4,
              fillColor: "#1976d2",
              color: "#fff",
              weight: 2,
              opacity: 1,
              fillOpacity: 0.8,
            },
          ).addTo(map);

          // 📌 Popup untuk setiap segmen
          const popup = `
                        <div style="font-size: 12px;">
                            <strong>${feature.properties.nama_segmen}</strong><br>
                            Ruas: ${feature.properties.ruas_jalan}<br>
                            Km: ${feature.properties.km_awal} - ${feature.properties.km_akhir}<br>
                            Kategori: <span style="color: ${feature.properties.color};">
                                ●
                            </span> ${feature.properties.kategori.toUpperCase()}<br>
                            Z-Score: ${feature.properties.zscore.toFixed(3)}<br>
                            Kecelakaan: ${feature.properties.accident_count}
                        </div>
                    `;

          layer.bindPopup(popup);

          // Click event
          layer.on("click", function () {
            console.log("Clicked segment:", feature.properties);
            selectedSegmen = feature;
          });
        },
      }).addTo(map);

      // Zoom ke extent segmen
      const bounds = segmenLayer.getBounds();
      map.fitBounds(bounds);
    })
    .catch((error) => {
      console.error("❌ Error loading segmen data:", error);
    });
}
```

---

### 3.3 Visualisasi Marker pada Peta

```
LEGENDA PETA INTERAKTIF:
═══════════════════════════════════════════

🔴 Marker MERAH BESAR (diameter ~20px)
   └─ Awal & Akhir dari RUAS JALAN (garis utama)
   └─ Contoh: Awal Jl. Soekarno-Hatta di (-7.6298, 111.5239)

🔵 Marker BIRU KECIL (diameter ~8px)
   └─ Awal & Akhir dari setiap SEGMEN JALAN
   └─ Contoh: Titik 1, Titik 2, dst di antara ruas

━━━ Garis BERWARNA (thickness 4px)
   ├─ 🔴 MERAH = Sangat Tinggi (Z-Score ≥ 1.5)
   ├─ 🟠 ORANGE = Tinggi (1.0 ≤ Z-Score < 1.5)
   ├─ 🟡 KUNING = Sedang (0.5 ≤ Z-Score < 1.0)
   ├─ 🟢 HIJAU = Rendah (0 ≤ Z-Score < 0.5)
   ├─ 🟩 HIJAU GELAP = Sangat Rendah (Z-Score < 0)
   └─ 🔵 BIRU (dashed) = Aman (Tidak ada kecelakaan)


CONTOH DATA DI PETA:
═══════════════════════════════════════════

Jl. Soekarno-Hatta (RUAS JALAN)
│
├─ [Titik 1] ──── Segmen 1 (Km 0-2.5) ──── [Titik 2]  🔴 Sangat Tinggi
├─ [Titik 2] ──── Segmen 2 (Km 2.5-5) ──── [Titik 3]  🟠 Tinggi
├─ [Titik 3] ──── Segmen 3 (Km 5-7) ────── [Titik 4]  🟡 Sedang
└─ [Titik 4] ──── Segmen 4 (Km 7-8.5) ──── [Titik 5]  🟢 Rendah
```

---

## 📊 RINGKASAN ALUR SISTEM

```
┌─────────────────────────────────────────────────────────┐
│ 1. UPLOAD DATA KECELAKAAN (Lat/Lon)                     │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 2. SISTEM OTOMATIS MENCOCOKKAN DENGAN SEGMEN            │
│    (Perpendicular Distance Algorithm)                   │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 3. HITUNG Z-SCORE PER SEGMEN                            │
│    (Identifikasi tingkat kerawanan)                     │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 4. GENERATE GEOJSON DENGAN WARNA KATEGORI               │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ 5. RENDER PETA INTERAKTIF (LEAFLET + LEAFLET.JS)       │
│    - Garis segmen berwarna berdasarkan kerawanan       │
│    - Marker awal/akhir segmen                          │
│    - Popup info saat diklik                            │
└─────────────────────────────────────────────────────────┘
```

---

## 🔑 POIN-POIN PENTING UNTUK LAPORAN TA

### 1. Keunikan Algoritma Pencocokkan

- ✅ Menggunakan **Perpendicular Distance** untuk akurasi tinggi
- ✅ Validasi proyeksi berada dalam rentang segmen (Along-track distance)
- ✅ Tolerance 50 meter (configurable)
- ✅ Otomatis saat data disimpan (hook pada method `save()`)

### 2. Pembagian Segmen

- ✅ Mode Manual: User klik di peta untuk tentukan titik pembagi
- ✅ Mode Otomatis: Gunakan Overpass API untuk cari persimpangan
- ✅ Menggunakan Geodesic Distance untuk akurasi geografis

### 3. Visualisasi

- ✅ Color-coded berdasarkan Z-Score (kerawanan)
- ✅ Leaflet.js untuk interaktivitas
- ✅ Real-time update data
- ✅ Filter tahun dan ruas jalan

### 4. Database Design

- ✅ Foreign Key: Kecelakaan → SegmenJalan
- ✅ Segmen menyimpan geometry dalam format GeoJSON
- ✅ Support untuk MultiLineString dan LineString

---

## 📚 REFERENSI KODE LENGKAP

Untuk detail lebih lanjut, lihat file-file berikut di project:

1. **[coreapp/models.py](coreapp/models.py)**
   - Model RuasJalan, SegmenJalan, Kecelakaan
   - Method `generate_segmen()`, `find_closest_segment()`

2. **[coreapp/views.py](coreapp/views.py)**
   - `map_view()`: View untuk halaman peta
   - `api_segmen_geojson()`: API untuk GeoJSON
   - `api_segmen_thresholds()`: API untuk threshold data

3. **[templates/coreapp/map/map.html](templates/coreapp/map/map.html)**
   - Frontend rendering dengan Leaflet.js
   - JavaScript untuk load dan visualisasi GeoJSON

---

**Terakhir diupdate:** 2026-07-01
**Dibuat untuk:** Laporan Tugas Akhir - Smart Accident System
**Author:** Development Team
