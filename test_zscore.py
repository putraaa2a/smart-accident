# Django Shell Script - Test Z-Score Calculation
# Jalankan dengan: python manage.py shell < test_zscore.py

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SmartAccident.settings')
django.setup()

from coreapp.models import RekapSegmen, AnalisisZScore, RuasJalan, SegmenJalan
import math

def test_zscore_calculation(tahun=None, ruas_id=None):
    """
    Test Z-score calculation untuk memastikan sama dengan Excel
    """
    print("\n" + "="*80)
    print("🧪 Z-SCORE CALCULATION TEST")
    print("="*80)
    
    if tahun is None:
        tahun = 2024
    
    print(f"\nTesting tahun: {tahun}")
    
    # Ambil satu ruas jalan untuk testing
    if ruas_id:
        ruas = RuasJalan.objects.get(id=ruas_id)
    else:
        ruas = RuasJalan.objects.first()
    
    if not ruas:
        print("❌ Tidak ada ruas jalan di database")
        return
    
    print(f"Ruas Jalan: {ruas.nama_ruas} (ID: {ruas.id})")
    
    # Ambil semua segmen di ruas ini
    segments = SegmenJalan.objects.filter(ruas_jalan=ruas)
    print(f"Total Segmen: {segments.count()}")
    
    # Ambil RekapSegmen untuk tahun ini
    rekap_list = RekapSegmen.objects.filter(
        periode_tahun=tahun,
        segmen_jalan__in=segments
    ).order_by('segmen_jalan__id')
    
    if not rekap_list.exists():
        print(f"❌ Tidak ada RekapSegmen untuk tahun {tahun} di ruas {ruas.nama_ruas}")
        return
    
    print(f"Data Rekap: {rekap_list.count()} records")
    print("\n" + "-"*80)
    print(f"{'Segmen':<30} | {'X (Jumlah)':<15} | {'Z-Score':<12} | {'Kategori':<15}")
    print("-"*80)
    
    # Kumpulkan nilai X (jumlah kecelakaan)
    x_values = []
    rekap_map = {}
    
    for rekap in rekap_list:
        x = float(rekap.jumlah_kecelakaan)
        x_values.append(x)
        rekap_map[rekap.segmen_jalan.id] = {
            'nama': rekap.segmen_jalan.nama_segmen,
            'x': x,
            'rekap': rekap
        }
    
    # Hitung Mean
    n = len(x_values)
    mean = sum(x_values) / n if n > 0 else 0
    
    # Hitung Sample Variance (N-1) - seperti Excel STDEV
    if n > 1:
        variance = sum((x - mean) ** 2 for x in x_values) / (n - 1)
    else:
        variance = 0
    
    stddev = math.sqrt(variance) if variance > 0 else 1
    
    print(f"\n📊 STATISTIK:")
    print(f"   n = {n}")
    print(f"   Mean (μ) = {mean:.3f}")
    print(f"   Variance = {variance:.3f}")
    print(f"   StdDev (σ) = {stddev:.3f}")
    
    print(f"\n🔢 DATA & Z-SCORE CALCULATION:")
    print("-"*80)
    
    # Hitung dan tampilkan Z-score untuk setiap segmen
    for segmen_id in sorted(rekap_map.keys()):
        data = rekap_map[segmen_id]
        x = data['x']
        rekap = data['rekap']
        
        # Rumus Z = (X - μ) / σ
        zscore = (x - mean) / stddev if stddev > 0 else 0
        
        # Cek AnalisisZScore di database
        try:
            analisis = AnalisisZScore.objects.get(
                segmen_jalan=rekap.segmen_jalan,
                tahun=tahun
            )
            db_zscore = float(analisis.nilai_zscore)
            db_kategori = analisis.kategori
            match = "✅" if abs(float(db_zscore) - zscore) < 0.001 else "❌"
        except AnalisisZScore.DoesNotExist:
            db_zscore = None
            db_kategori = None
            match = "⚠️"
        
        print(f"{data['nama']:<30} | {x:>12.1f}    | {zscore:>10.3f} | DB: {db_zscore if db_zscore else 'N/A':<10} {match}")
    
    print("\n" + "="*80)
    print("✅ TEST COMPLETE\n")

if __name__ == '__main__':
    # Test dengan tahun 2024
    test_zscore_calculation(tahun=2024)
    
    # Atau test dengan ruas tertentu
    # test_zscore_calculation(tahun=2024, ruas_id=1)
