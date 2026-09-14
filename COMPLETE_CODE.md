# 📄 Kode Lengkap File yang Diubah

## 1. signals.py (LENGKAP)

```python
"""
Django Signals untuk auto-assign kecelakaan ke segmen
CATATAN: Signal untuk perhitungan RekapSegmen dan AnalisisZScore telah dipindahkan ke views.py
agar perhitungan hanya dilakukan sekali setelah seluruh data upload selesai (bukan per row).
Ini meningkatkan performa ketika upload data masif.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import KecelakaanPreprosesing, RekapSegmen, AnalisisZScore, SegmenJalan


@receiver(post_save, sender=SegmenJalan)
def auto_assign_kecelakaan_ke_segmen_baru(sender, instance, created, **kwargs):
    """
    Trigger ketika SegmenJalan baru dibuat atau diupdate.
    Auto-assign data KecelakaanPreprosesing yang belum punya segmen atau yang cocok dengan segmen baru.

    Flow:
    1. Ketika segmen jalan baru dibuat
    2. Cari semua data preprocessing yang belum punya segmen (segmen_jalan is NULL)
    3. Untuk setiap data, coba assign ke segmen baru jika koordinatnya cocok
    """
    if created:
        print(f"\n{'='*70}")
        print(f"🚨 Signal: Segmen Jalan BARU dibuat: {instance.nama_segmen or f'Segmen {instance.km_awal}-{instance.km_akhir}'}")
        print(f"{'='*70}")

        # Cari semua data preprocessing yang belum punya segmen
        kecelakaan_tanpa_segmen = KecelakaanPreprosesing.objects.filter(segmen_jalan__isnull=True)
        print(f"📊 Ditemukan {kecelakaan_tanpa_segmen.count()} data preprocessing tanpa segmen")

        if kecelakaan_tanpa_segmen.exists():
            assigned_count = 0
            tahun_list = set()  # Track tahun yang ada assignment

            for kecelakaan in kecelakaan_tanpa_segmen:
                try:
                    # Coba find closest segment
                    kecelakaan.find_closest_segment()

                    # Jika berhasil di-assign (segmen_jalan tidak null setelah find_closest_segment)
                    if kecelakaan.segmen_jalan:
                        kecelakaan.save(update_fields=['segmen_jalan', 'updated_at'])
                        assigned_count += 1
                        tahun_list.add(kecelakaan.tanggal.year)
                        print(f"   ✅ Kecelakaan ({kecelakaan.tanggal} - {kecelakaan.kecamatan}) → {kecelakaan.segmen_jalan.nama_segmen}")

                except Exception as e:
                    print(f"   ❌ Error assigning kecelakaan {kecelakaan.id}: {str(e)}")

            print(f"\n📈 Total data yang di-assign: {assigned_count}/{kecelakaan_tanpa_segmen.count()}")

            # Update rekap dan Z-Score untuk tahun-tahun yang ada assignment
            if assigned_count > 0 and tahun_list:
                try:
                    print(f"\n🔄 Updating calculations untuk tahun: {sorted(tahun_list)}")
                    for tahun in tahun_list:
                        RekapSegmen.update_rekap(tahun)
                        AnalisisZScore.calculate_zscore(tahun)
                    print(f"✅ RekapSegmen dan AnalisisZScore berhasil di-update")
                except Exception as e:
                    print(f"❌ Error updating calculations: {str(e)}")
        else:
            print(f"✅ Tidak ada data preprocessing yang perlu di-assign")

        print(f"{'='*70}\n")
```

---

## 2. models.py - Method calculate_zscore() (PARTIAL)

Hanya bagian yang dimodifikasi dari method `AnalisisZScore.calculate_zscore()`:

```python
@staticmethod
def calculate_zscore(tahun=None):
    """Hitung Z-Score untuk setiap segmen PER RUAS JALAN dengan interval dinamis

    CATATAN: Pemanggilan RekapSegmen.update_rekap() telah dihapus dari sini karena
    sudah dilakukan di views.py sebelum fungsi ini dipanggil.
    Ini memastikan perhitungan tidak berjalan berulang-ulang saat upload data masif.
    """
    from django.db.models import Avg, StdDev, Max, Min
    import decimal

    if tahun is None or tahun == 0 or tahun == '0':
        tahun = 0

    # 2. Hapus data analisis Z-Score lama untuk tahun tersebut agar tidak duplikat
    AnalisisZScore.objects.filter(tahun=tahun).delete()

    # 3. Ambil semua daftar ruas jalan yang unik
    ruas_jalan_list = RuasJalan.objects.all().distinct()

    print(f"\n📊 Calculating Z-Score for {tahun} - Per Ruas Jalan (Dynamic Intervals)")
    print(f"{'='*80}")

    # ... (rest of the code remains the same)
```

---

## 3. views.py - Function upload_kecelakaan_preprosesing() (LENGKAP)

```python
def upload_kecelakaan_preprosesing(request):
    """Upload data kecelakaan preprocessing dari Excel/CSV

    Proses:
    1. Baca file Excel/CSV
    2. Validasi kolom yang diperlukan
    3. Simpan setiap baris ke database (tanpa menghitung rekap/zscore per row)
    4. Setelah semua data berhasil disimpan, hitung RekapSegmen dan AnalisisZScore
       untuk setiap tahun yang ada di data yang diupload

    Ini meningkatkan performa ketika upload data masif karena perhitungan hanya
    dilakukan sekali setelah seluruh data disimpan, bukan per row.
    """
    if request.method == 'POST':
        form = UploadKecelakaanPreprosesForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            try:
                # Parse Excel/CSV file
                if file.name.endswith('.csv'):
                    df = pd.read_csv(file, encoding='utf-8-sig')
                else:
                    df = pd.read_excel(file)

                # Validasi kolom yang diperlukan
                required_columns = ['tanggal', 'waktu', 'latitude', 'longitude',
                                   'korban_meninggal', 'korban_luka_berat',
                                   'korban_luka_ringan', 'kerugian_materi',
                                   'desa', 'kecamatan', 'kabupaten_kota', 'keterangan']

                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    messages.error(request, f'Kolom yang hilang: {", ".join(missing_columns)}')
                    return render(request, 'coreapp/kecelakaan/upload_preprosesing.html', {'form': form})

                # Check apakah nomor_kecelakaan ada (opsional)
                has_nomor = 'nomor_kecelakaan' in df.columns

                # Import data - Track tahun-tahun yang ada di data yang diupload
                count = 0
                errors = []
                tahun_set = set()  # Track tahun-tahun unik

                for idx, row in df.iterrows():
                    try:
                        # Parse waktu - handle berbagai format
                        waktu_obj = None
                        if pd.notna(row['waktu']):
                            waktu_val = row['waktu']
                            # Jika sudah dalam format time object
                            if isinstance(waktu_val, type(pd.Timestamp.now().time())):
                                waktu_obj = waktu_val
                            # Jika string
                            elif isinstance(waktu_val, str):
                                try:
                                    waktu_obj = pd.to_datetime(waktu_val).time()
                                except:
                                    raise ValueError(f"Format waktu '{waktu_val}' tidak valid (gunakan HH:MM:SS)")
                            # Jika Timestamp/datetime
                            else:
                                try:
                                    waktu_obj = pd.to_datetime(waktu_val).time()
                                except:
                                    raise ValueError(f"Kolom waktu berisi tanggal bukan jam. Gunakan format HH:MM:SS")

                        # Parse tanggal dan track tahunnya
                        tanggal_obj = pd.to_datetime(row['tanggal'])
                        tahun = tanggal_obj.year
                        tahun_set.add(tahun)

                        # Build create dict with nomor_kecelakaan jika available
                        create_data = {
                            'tanggal': tanggal_obj,
                            'waktu': waktu_obj,
                            'latitude': float(row['latitude']),
                            'longitude': float(row['longitude']),
                            'korban_meninggal': int(row['korban_meninggal']) if pd.notna(row['korban_meninggal']) else 0,
                            'korban_luka_berat': int(row['korban_luka_berat']) if pd.notna(row['korban_luka_berat']) else 0,
                            'korban_luka_ringan': int(row['korban_luka_ringan']) if pd.notna(row['korban_luka_ringan']) else 0,
                            'kerugian_materi': float(row['kerugian_materi']) if pd.notna(row['kerugian_materi']) else 0,
                            'desa': str(row['desa']) if pd.notna(row['desa']) else '',
                            'kecamatan': str(row['kecamatan']) if pd.notna(row['kecamatan']) else '',
                            'kabupaten_kota': str(row['kabupaten_kota']) if pd.notna(row['kabupaten_kota']) else '',
                            'keterangan': str(row['keterangan']) if pd.notna(row['keterangan']) else '',
                            'polres': request.user.profile.polres
                        }

                        # Tambah nomor_kecelakaan jika ada di file
                        if has_nomor and pd.notna(row['nomor_kecelakaan']):
                            create_data['nomor_kecelakaan'] = str(row['nomor_kecelakaan']).strip()

                        KecelakaanPreprosesing.objects.create(**create_data)
                        count += 1
                    except Exception as e:
                        errors.append(f"Baris {idx + 2}: {str(e)}")

                # ============================================================
                # SETELAH SEMUA DATA DISIMPAN, LAKUKAN PERHITUNGAN REKAP & ZSCORE
                # ============================================================
                if count > 0 and tahun_set:
                    print(f"\n{'='*80}")
                    print(f"📊 Starting calculations after importing {count} records...")
                    print(f"{'='*80}")

                    try:
                        # Hitung RekapSegmen dan AnalisisZScore untuk setiap tahun yang ada
                        for tahun in sorted(tahun_set):
                            print(f"\n🔄 Processing tahun {tahun}...")
                            print(f"   Step 1: Updating RekapSegmen for tahun {tahun}...")
                            RekapSegmen.update_rekap(tahun)

                            print(f"   Step 2: Calculating AnalisisZScore for tahun {tahun}...")
                            AnalisisZScore.calculate_zscore(tahun)
                            print(f"   ✅ Completed for tahun {tahun}")

                        print(f"\n{'='*80}")
                        print(f"✅ All calculations completed successfully!")
                        print(f"{'='*80}\n")
                    except Exception as calc_error:
                        print(f"\n❌ Error during calculations: {str(calc_error)}")
                        messages.warning(request,
                            f'Data berhasil diimport ({count} records), namun ada error saat perhitungan: {str(calc_error)}')
                        return redirect('kecelakaan_preprosesing_list')

                if errors and len(errors) <= 10:
                    messages.warning(request, f'Berhasil import {count} data, tapi ada beberapa error:\n' + '\n'.join(errors[:5]))
                else:
                    messages.success(request, f'Berhasil import {count} data kecelakaan preprocessing.')

                return redirect('kecelakaan_preprosesing_list')
            except Exception as e:
                messages.error(request, f'Error saat memproses file: {str(e)}')
    else:
        form = UploadKecelakaanPreprosesForm()

    return render(request, 'coreapp/kecelakaan/upload_preprosesing.html', {'form': form})
```

---

## 🔍 Key Changes Summary

### signals.py

- **Dihapus**: 2 receiver (KecelakaanPreprosesing post_save & post_delete)
- **Dipertahankan**: 1 receiver (SegmenJalan post_save)
- **Lines**: ~60 lines → ~55 lines

### models.py

- **Dihapus**: 1 baris (`RekapSegmen.update_rekap(tahun)`)
- **Lokasi**: Dalam method `calculate_zscore()` di class `AnalisisZScore`
- **Lines affected**: ~5 lines

### views.py

- **Dimodifikasi**: Function `upload_kecelakaan_preprosesing()`
- **Ditambah**:
  - Variable `tahun_set` untuk tracking
  - Baris `tahun_set.add(tahun)` dalam loop
  - Block perhitungan setelah loop (~45 lines)
- **Total lines**: ~90 lines → ~135 lines

---

## ✅ Verification

Setelah menerapkan perubahan, pastikan:

1. **File upload Excel berhasil** (tanpa error pada parsing)
2. **Data masuk ke database** (check via Django admin)
3. **RekapSegmen terupdate** (check query)
4. **AnalisisZScore terupdate** (check query)
5. **Console log menampilkan** "Starting calculations" & "Completed"
6. **Upload 1000 data selesai** dalam < 1 menit
7. **RAM stabil** saat upload

---

## 🚀 Deployment

1. Backup database (optional tapi recommended)
2. Update `signals.py` dengan kode baru
3. Update `models.py` dengan kode baru
4. Update `views.py` dengan kode baru
5. Restart Django server: `python manage.py runserver` atau `systemctl restart gunicorn`
6. Test upload data kecil terlebih dahulu
7. Monitor logs saat upload data besar

**Tidak perlu migration** karena tidak ada perubahan database schema.
