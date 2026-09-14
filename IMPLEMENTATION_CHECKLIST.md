# ✅ Implementation Verification Checklist

## Sebelum Upload Produksi

### 1. File Verification

- [ ] `coreapp/signals.py` - Hapus receiver KecelakaanPreprosesing
  - Verifikasi: Hanya ada 1 receiver (SegmenJalan)
  - Command: `grep -n "@receiver" coreapp/signals.py`
  - Expected: 1 match (SegmenJalan)

- [ ] `coreapp/models.py` - Hapus `RekapSegmen.update_rekap()` dari calculate_zscore
  - Verifikasi: Baris `RekapSegmen.update_rekap(tahun)` tidak ada di dalam method
  - Command: `grep -A 10 "def calculate_zscore" coreapp/models.py | grep "update_rekap"`
  - Expected: No match (empty)

- [ ] `coreapp/views.py` - Tambah perhitungan setelah loop
  - Verifikasi: Ada variable `tahun_set` dan loop for tahun
  - Command: `grep -n "tahun_set" coreapp/views.py`
  - Expected: Multiple matches (add, if, for loop)

### 2. Syntax Validation

- [ ] Python syntax check (no import errors)

  ```bash
  python manage.py check
  # Expected: System check identified no issues (0 silenced).
  ```

- [ ] Django migrations (none needed)

  ```bash
  python manage.py makemigrations --dry-run
  # Expected: No changes detected
  ```

- [ ] Import test
  ```bash
  python manage.py shell
  >>> from coreapp.models import RekapSegmen, AnalisisZScore
  >>> from coreapp.views import upload_kecelakaan_preprosesing
  >>> print("✅ All imports OK")
  ```

### 3. Database State

- [ ] Database backup created (optional)

  ```bash
  python manage.py dumpdata > backup_before_change.json
  ```

- [ ] Check existing data integrity
  ```bash
  python manage.py shell
  >>> from coreapp.models import KecelakaanPreprosesing, RekapSegmen, AnalisisZScore
  >>> print(f"KecelakaanPreprosesing: {KecelakaanPreprosesing.objects.count()}")
  >>> print(f"RekapSegmen: {RekapSegmen.objects.count()}")
  >>> print(f"AnalisisZScore: {AnalisisZScore.objects.count()}")
  ```

### 4. Server Startup

- [ ] Server starts without errors

  ```bash
  python manage.py runserver
  # Check: No AttributeError, ImportError, or SyntaxError
  ```

- [ ] View accessible
  ```bash
  curl http://localhost:8000/upload/kecelakaan/preprosesing/
  # Expected: 200 OK or 302 redirect to login
  ```

---

## Testing Phase

### Phase 1: Small Data Test

**File**: 10 rows, 1 tahun (2024)

- [ ] Upload berhasil

  ```
  Expected message: "Berhasil import 10 data kecelakaan preprocessing."
  ```

- [ ] Console log menampilkan perhitungan

  ```
  Expected:
    "Starting calculations after importing 10 records..."
    "Processing tahun 2024..."
    "Step 1: Updating RekapSegmen for tahun 2024..."
    "Step 2: Calculating AnalisisZScore for tahun 2024..."
    "Completed for tahun 2024"
  ```

- [ ] Data tersimpan di database

  ```bash
  python manage.py shell
  >>> from coreapp.models import KecelakaanPreprosesing, RekapSegmen, AnalisisZScore
  >>> print(f"KecelakaanPreprosesing: {KecelakaanPreprosesing.objects.filter(tanggal__year=2024).count()}")
  >>> print(f"RekapSegmen 2024: {RekapSegmen.objects.filter(periode_tahun=2024).count()}")
  >>> print(f"AnalisisZScore 2024: {AnalisisZScore.objects.filter(tahun=2024).count()}")
  # Expected: 10, >0, >0
  ```

- [ ] Hasil perhitungan valid
  ```bash
  python manage.py shell
  >>> from coreapp.models import AnalisisZScore
  >>> zscores = AnalisisZScore.objects.filter(tahun=2024)
  >>> for z in zscores[:5]:
  ...     print(f"{z.segmen_jalan.nama_segmen}: {z.nilai_zscore} ({z.kategori})")
  # Expected: Lihat Z-score values dan category
  ```

### Phase 2: Medium Data Test

**File**: 100 rows, 1 tahun (2024)

- [ ] Upload berhasil & cepat (< 10 detik)
- [ ] Console log menampilkan "All calculations completed successfully!"
- [ ] Data & perhitungan valid (sama seperti Phase 1)

### Phase 3: Large Data Test

**File**: 1000 rows, mixed tahun (2023: 500, 2024: 500)

- [ ] Upload berhasil & cepat (< 1 menit)
- [ ] Console log menampilkan

  ```
  Processing tahun 2023...
  Processing tahun 2024...
  ```

- [ ] Data tersimpan dengan benar

  ```bash
  python manage.py shell
  >>> from coreapp.models import KecelakaanPreprosesing
  >>> print(f"2023: {KecelakaanPreprosesing.objects.filter(tanggal__year=2023).count()}")  # Expected: 500
  >>> print(f"2024: {KecelakaanPreprosesing.objects.filter(tanggal__year=2024).count()}")  # Expected: 500
  ```

- [ ] RekapSegmen & AnalisisZScore ada untuk kedua tahun

  ```bash
  python manage.py shell
  >>> from coreapp.models import RekapSegmen, AnalisisZScore
  >>> print(f"RekapSegmen 2023: {RekapSegmen.objects.filter(periode_tahun=2023).count()}")
  >>> print(f"RekapSegmen 2024: {RekapSegmen.objects.filter(periode_tahun=2024).count()}")
  >>> print(f"AnalisisZScore 2023: {AnalisisZScore.objects.filter(tahun=2023).count()}")
  >>> print(f"AnalisisZScore 2024: {AnalisisZScore.objects.filter(tahun=2024).count()}")
  # Expected: >0 untuk semua
  ```

- [ ] RAM usage stabil (tidak spike drastis)
  ```bash
  # Monitor di server: top, htop, atau metrics
  # Expected: RAM ≈ normal usage, tidak crash
  ```

### Phase 4: Edge Cases

- [ ] Upload dengan error di beberapa baris

  ```
  Expected:
    "Berhasil import X data, tapi ada beberapa error:"
    "Baris X: [error message]"
  ```

- [ ] Upload dengan nomor_kecelakaan kosong

  ```
  Expected: Data tetap tersimpan (nomor_kecelakaan opsional)
  ```

- [ ] Upload file CSV instead of Excel

  ```
  Expected: Berhasil sama seperti Excel
  ```

- [ ] Delete 1 kecelakaan

  ```bash
  python manage.py shell
  >>> from coreapp.models import KecelakaanPreprosesing
  >>> obj = KecelakaanPreprosesing.objects.first()
  >>> obj.delete()
  # Expected: Tidak ada signal yang trigger perhitungan
  # (Check console: tidak ada output dari signal)
  ```

- [ ] Buat segmen jalan baru
  ```bash
  python manage.py shell
  >>> from coreapp.models import RuasJalan, SegmenJalan
  >>> ruas = RuasJalan.objects.first()
  >>> seg = SegmenJalan.objects.create(
  ...     ruas_jalan=ruas,
  ...     km_awal=0, km_akhir=5, panjang_segmen=5
  ... )
  # Expected: Console log menampilkan auto-assign & perhitungan
  # (Signal untuk SegmenJalan tetap aktif)
  ```

### Phase 5: Performance Benchmark

**Compare before & after**

| Metric                | Before         | After            | Status |
| --------------------- | -------------- | ---------------- | ------ |
| Upload 1000 data time | 2-5 min        | < 1 min          | ✅     |
| RAM spike             | ↑↑↑            | ↑                | ✅     |
| CPU usage             | High sustained | Peak then normal | ✅     |
| Gunicorn crashes      | Yes            | No               | ✅     |
| Result accuracy       | ✓              | ✓                | ✅     |

---

## Troubleshooting

### Issue: Console log tidak menampilkan "Starting calculations"

**Diagnosis**:

- [ ] Cek apakah `tahun_set` ada di dalam if statement
- [ ] Cek apakah variable `count > 0`
- [ ] Cek apakah `tahun_set` tidak kosong

**Solution**:

```python
# Di console untuk verify
print(f"Count: {count}, Tahun Set: {tahun_set}")
```

### Issue: Error saat perhitungan: "name 'RekapSegmen' is not defined"

**Solution**:

- Pastikan import sudah ada di views.py:
  ```python
  from .models import RekapSegmen, AnalisisZScore, KecelakaanPreprosesing
  ```

### Issue: Z-Score values jauh berbeda dari sebelumnya

**Diagnosis**:

- Ini normal jika data banyak berubah
- Bandingkan dengan calculate_zscore() manual untuk verify

### Issue: Upload berjalan tapi perhitungan error

**Action**:

- Check console untuk error message
- Verify data di database
- Pastikan tidak ada missing required fields

---

## Rollback Procedure (Jika diperlukan)

Jika ada masalah, kembalikan ke versi sebelumnya:

```bash
# Option 1: Git rollback (jika menggunakan git)
git checkout HEAD~1 coreapp/signals.py coreapp/models.py coreapp/views.py
python manage.py runserver

# Option 2: Manual rollback
# Copy kode original dari backup
# Re-add receiver untuk KecelakaanPreprosesing di signals.py
# Re-add RekapSegmen.update_rekap() di models.py
# Remove perhitungan batch dari views.py
```

---

## Sign-Off

- [ ] All Phase 1-4 tests passed
- [ ] Performance benchmark meets expectations (Phase 5)
- [ ] No errors in production logs
- [ ] Database integrity verified
- [ ] Team members notified
- [ ] Documentation updated
- [ ] Ready for production deployment

**Deployment Date**: ******\_\_\_******  
**Deployed By**: ******\_\_\_******  
**Verified By**: ******\_\_\_******
