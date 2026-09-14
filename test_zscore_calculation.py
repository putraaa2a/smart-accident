#!/usr/bin/env python
"""
Test script untuk verify perhitungan Z-Score match dengan Excel
Jalankan: python manage.py shell < test_zscore_calculation.py
"""

import os
import django
import sys
import math

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SmartAccident.settings')
django.setup()

from coreapp.models import RekapSegmen, RuasJalan, SegmenJalan, AnalisisZScore

print("\n" + "="*80)
print("🧪 TEST Z-SCORE CALCULATION vs EXCEL")
print("="*80)

# Data dari Excel
excel_data = {
    'Segmen 1': 16,
    'Segmen 2': 8,
    'Segmen 3': 23,
    'Segmen 4': 10,
    'Segmen 5': 16,
    'Segmen 6': 8,
    'Segmen 7': 15,
    'Segmen 8': 12,
}

excel_mean = 13.500
excel_stddev = 4.743

# Calculate using our formula (Population variance - N)
values = list(excel_data.values())
n = len(values)

# Manual calculation
manual_mean = sum(values) / n
sum_squared_diff = sum((x - manual_mean) ** 2 for x in values)
manual_variance = sum_squared_diff / n  # Population variance (N)
manual_stddev = math.sqrt(manual_variance)

print(f"\n📊 EXCEL DATA:")
print(f"   Data: {list(excel_data.values())}")
print(f"   Excel Mean: {excel_mean}")
print(f"   Excel StdDev: {excel_stddev}")

print(f"\n🔢 MANUAL CALCULATION (Population Variance - N):")
print(f"   Calculated Mean: {manual_mean:.3f}")
print(f"   Sum of Squared Diff: {sum_squared_diff:.3f}")
print(f"   Variance (N): {manual_variance:.3f}")
print(f"   StdDev: {manual_stddev:.3f}")

print(f"\n✅ MATCH CHECK:")
mean_match = abs(manual_mean - excel_mean) < 0.001
stddev_match = abs(manual_stddev - excel_stddev) < 0.001
print(f"   Mean match: {mean_match} (Diff: {abs(manual_mean - excel_mean):.6f})")
print(f"   StdDev match: {stddev_match} (Diff: {abs(manual_stddev - excel_stddev):.6f})")

print(f"\n📈 Z-SCORE CALCULATION:")
print(f"{'Segmen':<12} {'Jumlah':<8} {'(X-μ)':<10} {'Z-Score':<10} {'Status'}")
print(f"{'-'*50}")

for segmen_name, jumlah in excel_data.items():
    zscore = (jumlah - manual_mean) / manual_stddev
    diff = jumlah - manual_mean
    print(f"{segmen_name:<12} {jumlah:<8} {diff:>9.3f} {zscore:>9.3f} ✓")

# Check with database if data exists
print(f"\n📁 CHECKING DATABASE:")
try:
    rekaps = RekapSegmen.objects.filter(periode_tahun=2024).order_by('segmen_jalan_id')[:8]
    if rekaps.exists():
        print(f"   Found {rekaps.count()} RekapSegmen records for tahun 2024")
        
        db_values = [float(r.jumlah_kecelakaan) for r in rekaps]
        db_mean = sum(db_values) / len(db_values)
        db_sum_sq = sum((x - db_mean) ** 2 for x in db_values)
        db_variance = db_sum_sq / len(db_values)
        db_stddev = math.sqrt(db_variance)
        
        print(f"\n   DB Mean: {db_mean:.3f}")
        print(f"   DB StdDev: {db_stddev:.3f}")
        print(f"   Match with Excel: Mean={abs(db_mean - excel_mean) < 0.001}, StdDev={abs(db_stddev - excel_stddev) < 0.001}")
    else:
        print(f"   ⚠️ No RekapSegmen data found for tahun 2024")
except Exception as e:
    print(f"   ⚠️ Error checking database: {e}")

print(f"\n{'='*80}")
print("✅ TEST COMPLETE - If all values match Excel, calculation is CORRECT")
print(f"{'='*80}\n")
