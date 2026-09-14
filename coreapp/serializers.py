from rest_framework import serializers
from .models import AhcPreprosesing, KecelakaanPreprosesing, KmeansPreprosesing


class KecelakaanPreprosesingSerializer(serializers.ModelSerializer):
    """Serializer untuk menampilkan data KecelakaanPreprosesing dalam API."""

    class Meta:
        model = KecelakaanPreprosesing
        fields = [
            'id',
            'nomor_kecelakaan',
            'tanggal',
            'waktu',
            'latitude',
            'longitude',
            'segmen_jalan',
            'korban_meninggal',
            'korban_luka_berat',
            'korban_luka_ringan',
            'kerugian_materi',
            'desa',
            'kecamatan',
            'kabupaten_kota',
            'keterangan',
            'polres',
            'created_at',
            'updated_at',
        ]
        depth = 0


class AhcPreprosesingSerializer(serializers.ModelSerializer):
    """Serializer read-only untuk data preprocessing AHC."""

    class Meta:
        model = AhcPreprosesing
        fields = [
            'id', 'no_referensi', 'umur', 'tkp', 'penyebab', 'hari',
            'tanggal', 'jam', 'jenis_kendaraan', 'tipe_kendaraan',
            'kerugian_material', 'created_at',
        ]


class KmeansPreprosesingSerializer(serializers.ModelSerializer):
    """Serializer read-only untuk data preprocessing K-Means."""

    class Meta:
        model = KmeansPreprosesing
        fields = [
            'id', 'no_referensi', 'umur', 'tkp', 'penyebab', 'hari',
            'tanggal', 'jam', 'jenis_kendaraan', 'tipe_kendaraan',
            'kerugian_material', 'created_at',
        ]
