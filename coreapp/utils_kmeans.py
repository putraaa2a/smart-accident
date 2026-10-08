import os
import json
import requests
import pandas as pd
import numpy as np
from io import StringIO
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from .models import AIConfig, KmeansPreprosesing
from .ai_utils import parse_ai_json, request_ai_completion


def _save_uploaded_kmeans_data(df):
    """Simpan baris file upload K-Means ke tabel khusus sebelum transformasi."""
    from decimal import Decimal, InvalidOperation
    from .models import KmeansPreprosesing

    # Normalisasi nama kolom file agar sesuai dengan field tabel.
    normalized = {str(column).strip().lower(): column for column in df.columns}

    def value(row, name, default=''):
        source = normalized.get(name.lower())
        result = row[source] if source is not None else default
        return default if pd.isna(result) else result

    def to_date(raw_value):
        parsed = pd.to_datetime(raw_value, errors='coerce')
        return None if pd.isna(parsed) else parsed.date()

    def to_decimal(raw_value):
        try:
            digits = ''.join(character for character in str(raw_value) if character.isdigit() or character in '.-')
            return Decimal(digits or '0')
        except (InvalidOperation, ValueError):
            return Decimal('0')

    records = []
    for _, row in df.iterrows():
        age = pd.to_numeric(value(row, 'umur', 0), errors='coerce')
        records.append(KmeansPreprosesing(
            no_referensi=str(value(row, 'no')).strip() or None,
            umur=0 if pd.isna(age) else int(age),
            tkp=str(value(row, 'tkp')).strip(),
            penyebab=str(value(row, 'penyebab')).strip(),
            hari=str(value(row, 'hari')).strip(),
            tanggal=to_date(value(row, 'tanggal', None)),
            jam=str(value(row, 'jam')).strip(),
            jenis_kendaraan=str(value(row, 'jenis kendaraan')).strip(),
            tipe_kendaraan=str(value(row, 'tipe kendaraan')).strip(),
            kerugian_material=to_decimal(value(row, 'kerugian material', 0)),
        ))
    if records:
        KmeansPreprosesing.objects.bulk_create(records, batch_size=1000)

# ================================
# PREPROCESSING DATA K-MEANS HELPERS
# ================================
def _perform_kmeans_preprocessing(df):
    """Helper function to process dataframe for K-Means"""
    df.replace('-', np.nan, inplace=True)
    df.columns = df.columns.str.strip()

    # Rename kolom ke format standar
    col_map = {}
    for col in df.columns:
        low = col.lower().replace(' ', '_')
        if 'jam' in low:               col_map[col] = 'Jam'
        elif 'hari' in low:            col_map[col] = 'Hari'
        elif 'tanggal' in low:         col_map[col] = 'Tanggal'
        elif 'no' == low:              col_map[col] = 'No'
        elif 'umur' in low or 'usia' in low: col_map[col] = 'Umur'
        elif 'tkp' in low or 'lokasi' in low: col_map[col] = 'TKP'
        elif 'penyebab' in low:        col_map[col] = 'Penyebab'
        elif 'jenis_kendaraan' in low or 'jenis kendaraan' == col.lower(): col_map[col] = 'Jenis Kendaraan'
        elif 'tipe_kendaraan' in low or 'tipe kendaraan' == col.lower():  col_map[col] = 'Tipe Kendaraan'
        elif 'kerugian' in low:        col_map[col] = 'Kerugian Material'
    df = df.rename(columns=col_map)

    # Pastikan Umur adalah numerik
    if 'Umur' in df.columns:
        df['Umur'] = pd.to_numeric(df['Umur'], errors='coerce').fillna(0)
    else:
        df['Umur'] = 0

    def jam_ke_numerik(val):
        try:
            s = str(val).strip().replace(',', '.').replace(' ', '')
            if ':' in s:
                parts = s.split(':')
                return float(parts[0]) + float(parts[1]) / 60.0
            elif '.' in s:
                parts = s.split('.')
                return float(parts[0]) + float(parts[1]) / 60.0
            else:
                return float(s)
        except:
            return np.nan

    if 'Jam' in df.columns:
        df['Jam_Numerik'] = df['Jam'].apply(jam_ke_numerik)
    else:
        df['Jam_Numerik'] = 0

    hari_map = {
        'senin': 1, 'selasa': 2, 'rabu': 3,
        'kamis': 4, 'jumat': 5, 'sabtu': 6, 'minggu': 7
    }
    if 'Hari' in df.columns:
        df['Hari_Numerik'] = df['Hari'].str.strip().str.lower().map(hari_map).fillna(0)
    else:
        df['Hari_Numerik'] = 0

    # Filter data yang tidak valid
    df = df.dropna(subset=['Jam_Numerik', 'Hari_Numerik'])
    df = df[df['Hari_Numerik'] > 0]
    df = df.reset_index(drop=True)

    # ─────────────────────────────────────────────────
    # AGREGASI LANJUTAN (Umur, Kendaraan, Faktor)
    # ─────────────────────────────────────────────────
    
    # Faktor mapping
    pengemudi_keywords = ['konsentrasi', 'mengantuk', 'apill', 'arus', 'marka', 'pintu', 'jalur', 'kiri', 'petugas', 'ngerem', 'sein', 'laju', 'utama', 'jarak']
    jalan_keywords = ['lubang', 'gelincir', 'licin', 'rusak']
    kendaraan_keywords = ['ban', 'rem', 'lampu', 'mesin']
    lingkungan_keywords = ['cuaca', 'hujan', 'kabut', 'gelap']

    def get_faktor(p):
        p = str(p).lower()
        if any(k in p for k in pengemudi_keywords): return 'Pengemudi'
        if any(k in p for k in jalan_keywords): return 'Jalan'
        if any(k in p for k in kendaraan_keywords): return 'Kendaraan'
        if any(k in p for k in lingkungan_keywords): return 'Lingkungan'
        return 'Pengemudi' # Default

    df['Faktor'] = df['Penyebab'].apply(get_faktor)
    
    # Kendaraan mapping
    def get_tipe_group(j):
        j = str(j).lower()
        if 'motor' in j: return 'Motor'
        if 'mobil' in j or 'pribadi' in j: return 'Mobil'
        if 'truk' in j or 'bus' in j or 'fuso' in j or 'box' in j: return 'Truk/Bus'
        return 'Lainnya'

    df['Tipe_Group'] = df['Jenis Kendaraan'].apply(get_tipe_group)

    # Jam_Slot (0-23)
    df['Jam_Slot'] = df['Jam_Numerik'].apply(
        lambda x: 0 if int(x) >= 24 else int(x) if pd.notna(x) else 0
    )

    # Hitung aggregasi per slot (Hari, Jam)
    summary_df = df.groupby(['Hari_Numerik', 'Jam_Slot']).agg(
        Jumlah_Kejadian=('Jam_Slot', 'count'),
        Rerata_Umur=('Umur', 'mean'),
        Motor=('Tipe_Group', lambda x: (x == 'Motor').sum()),
        Mobil=('Tipe_Group', lambda x: (x == 'Mobil').sum()),
        Truk_Bus=('Tipe_Group', lambda x: (x == 'Truk/Bus').sum()),
        Faktor_Pengemudi=('Faktor', lambda x: (x == 'Pengemudi').sum()),
        Faktor_Jalan=('Faktor', lambda x: (x == 'Jalan').sum()),
        Faktor_Kendaraan=('Faktor', lambda x: (x == 'Kendaraan').sum()),
        Faktor_Lingkungan=('Faktor', lambda x: (x == 'Lingkungan').sum()),
    ).reset_index()

    # Periode Waktu (Dini, Pagi, Siang, Malam)
    summary_df['Dini Hari']  = summary_df['Jam_Slot'].apply(lambda x: 1 if 0 <= x < 6 else 0)
    summary_df['Pagi Hari']  = summary_df['Jam_Slot'].apply(lambda x: 1 if 6 <= x < 12 else 0)
    summary_df['Siang Hari'] = summary_df['Jam_Slot'].apply(lambda x: 1 if 12 <= x < 18 else 0)
    summary_df['Malam Hari'] = summary_df['Jam_Slot'].apply(lambda x: 1 if 18 <= x < 24 else 0)

    # Label & Formatting
    hari_label = {1:'Senin',2:'Selasa',3:'Rabu',4:'Kamis',5:'Jumat',6:'Sabtu',7:'Minggu'}
    summary_df['Hari'] = summary_df['Hari_Numerik'].map(hari_label)
    summary_df['Jam']  = summary_df['Jam_Slot'].apply(lambda x: f"{x:02d}:00")
    
    # Final column ordering & renaming
    summary_df = summary_df.sort_values(['Hari_Numerik', 'Jam_Slot']).reset_index(drop=True)
    summary_df['No'] = summary_df.index + 1
    
    # Simpan Jam_Numerik asli untuk clustering
    summary_df['Jam_Numerik_Original'] = summary_df['Jam_Slot']
    
    summary_df = summary_df.rename(columns={
        'Jam_Slot': 'Jam_Numerik',
        'Rerata_Umur': 'Umur',
        'Truk_Bus': 'Truk/Bus',
        'Faktor_Pengemudi': 'Faktor Pengemudi',
        'Faktor_Jalan': 'Faktor Jalan',
        'Faktor_Kendaraan': 'Faktor Kendaraan',
        'Faktor_Lingkungan': 'Faktor Lingkungan',
    })

    # Bulatkan Umur
    summary_df['Umur'] = summary_df['Umur'].round(0).astype(int)

    # Re-map Jumlah_Kejadian ke "Jumlah Kejadian" untuk preview
    summary_df['Jumlah Kejadian'] = summary_df['Jumlah_Kejadian']
    
    # Pilih Kolom yang ditampilkan (Sesuai Permintaan User)
    summary_df = summary_df[[
        'No', 'Hari', 'Jam', 'Umur', 'Jumlah Kejadian', 
        'Motor', 'Mobil', 'Truk/Bus', 
        'Faktor Pengemudi', 'Faktor Jalan', 'Faktor Kendaraan', 'Faktor Lingkungan',
        'Dini Hari', 'Pagi Hari', 'Siang Hari', 'Malam Hari',
        'Hari_Numerik', 'Jam_Numerik', 'Jumlah_Kejadian' # Tetap bawa ini untuk proses_cluster
    ]]

    for col in summary_df.columns:
        if pd.api.types.is_datetime64_any_dtype(summary_df[col]):
            summary_df[col] = summary_df[col].dt.strftime('%d %B %Y')
        elif summary_df[col].dtype == object:
            summary_df[col] = summary_df[col].apply(
                lambda x: x.strftime('%d %B %Y') if hasattr(x, 'strftime') else x
            )
            
    return summary_df


# ================================
# PREPROCESSING DATA K-MEANS VIEW
# ================================
@login_required(login_url='login')
def preprocessing(request):
    context = {}
    show_all = request.GET.get('show_all') == '1'
    use_db = request.GET.get('use_db') == '1'

    # =========================
    # 1️⃣ PROSES INPUT (POST/DB)
    # =========================
    df = None
    
    if request.method == "POST" or use_db:
        # Reset session
        for key in ['hasil_cluster', 'summary_cluster', 'jumlah_cluster', 'jumlah_data',
                'silhouette_score', 'X_scaled', 'summary_df', 'jumlah_data_asli',
                'ai_dashboard_analysis', 'ai_recommendation_data']:
            request.session.pop(f'kmeans_{key}', None)

        if use_db:
            data_db = KmeansPreprosesing.objects.all().values()
            if not data_db:
                messages.error(request, "Data di database masih kosong.")
                return redirect('cluster_data_list')
            df = pd.DataFrame(list(data_db))
            # Map database fields to standard names
            df = df.rename(columns={
                'tkp': 'TKP', 'penyebab': 'Penyebab', 'hari': 'Hari',
                'tanggal': 'Tanggal', 'jam': 'Jam', 'umur': 'Umur',
                'jenis_kendaraan': 'Jenis Kendaraan', 'tipe_kendaraan': 'Tipe Kendaraan',
                'kerugian_material': 'Kerugian Material'
            })
            request.session['kmeans_uploaded_file_name'] = "Database K-Means"
        else:
            file = request.FILES.get('file')
            if file:
                df = pd.read_excel(file)
                request.session['kmeans_uploaded_file_name'] = file.name
                _save_uploaded_kmeans_data(df)

        if df is not None:
            request.session['kmeans_jumlah_data_asli'] = len(df)
            summary_df = _perform_kmeans_preprocessing(df)
            
            # Simpan ke session
            request.session['kmeans_summary_df'] = summary_df.to_dict(orient='records')
            request.session['kmeans_jumlah_data_bersih'] = len(summary_df)
            request.session.modified = True

            preview_df = summary_df.head(10) if not show_all else summary_df
            context['preview'] = preview_df.to_dict(orient='records')
            context['is_full_preview'] = show_all
            context['jumlah_data_bersih'] = len(summary_df)
            context['jumlah_data_awal'] = len(df)

    # ─────────────────────────────────────────────────────
    # 2️⃣ LOAD DARI SESSION (GET request / kembali ke halaman)
    # ─────────────────────────────────────────────────────
    summary_json = request.session.get('kmeans_summary_df')
    if summary_json:
        if isinstance(summary_json, list):
            df = pd.DataFrame(summary_json)
        else:
            try:
                df = pd.read_json(StringIO(summary_json), orient='records')
            except Exception:
                df = pd.DataFrame(summary_json)

        context['preview']            = df.to_dict(orient='records') if show_all else df.head(10).to_dict(orient='records')
        context['is_full_preview']    = show_all
        context['jumlah_data_bersih'] = len(df)

    # Tampilkan hasil cluster dari session (jika sudah pernah proses)
    hasil_cluster_session = request.session.get('kmeans_hasil_cluster')
    k_session             = request.session.get('kmeans_k')
    show_all_hasil        = request.GET.get('show_all_hasil') == '1'

    if hasil_cluster_session and k_session:
        context['hasil_cluster'] = hasil_cluster_session if show_all_hasil else hasil_cluster_session[:10]
        context['is_full_hasil'] = show_all_hasil
        context['k']             = k_session

    return render(request, 'coreapp/k-means/preprocessing.html', context)


# ================================
# RESET K-MEANS VIEW
# ================================
@login_required(login_url='login')
def reset_k_means(request):
    keys = ['hasil_cluster', 'summary_cluster', 'jumlah_cluster', 'jumlah_data',
            'silhouette_score', 'X_scaled', 'summary_df', 'uploaded_file_name', 
            'jumlah_data_asli', 'ai_dashboard_analysis', 'ai_recommendation_data']
    for key in keys:
        request.session.pop(f'kmeans_{key}', None)
    return redirect('preprocessing')


# ==========================================
# PROSES K-MEANS CLUSTERING VIEW
# ==========================================
@login_required(login_url='login')
def proses_cluster(request):
    if request.method != "GET":
        return redirect('preprocessing')

    try:
        k = int(request.GET.get('k', 3))
    except ValueError:
        k = 3
    k = max(2, min(k, 3))

    summary_json = request.session.get('kmeans_summary_df')
    if not summary_json:
        return redirect('preprocessing')

    if isinstance(summary_json, list):
        df = pd.DataFrame(summary_json)
    else:
        try:
            df = pd.read_json(StringIO(summary_json), orient='records')
        except Exception:
            df = pd.DataFrame(summary_json)

    if df.empty:
        return redirect('preprocessing')

    # ─────────────────────────────────────────────────────
    # FITUR K-MEANS: Hari + Jam + Jumlah_Kejadian
    # ─────────────────────────────────────────────────────
    feature_cols = [col for col in ['Hari_Numerik', 'Jam_Numerik', 'Jumlah_Kejadian']
                    if col in df.columns]

    if not feature_cols:
        return redirect('preprocessing')

    X = df[feature_cols].fillna(0)

    if len(X) < k:
        k = len(X)

    try:
        scaler   = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Hitung Data Elbow (Inertia untuk K=1 s/d 10)
        elbow_data = []
        K_limit = min(11, len(X_scaled) + 1)
        for i in range(1, K_limit):
            km_temp = KMeans(n_clusters=i, random_state=42, n_init=10)
            km_temp.fit(X_scaled)
            elbow_data.append(float(km_temp.inertia_))
        request.session['kmeans_elbow_data'] = elbow_data

        model = KMeans(n_clusters=k, random_state=42, n_init=10)
        df['Cluster'] = model.fit_predict(X_scaled) + 1  # 1,2,3

    except Exception as e:
        print("ERROR CLUSTERING:", e)
        return redirect('preprocessing')

    # ─────────────────────────────────────────────────────
    # LABELING: berdasarkan rata-rata Jumlah_Kejadian per cluster
    # ─────────────────────────────────────────────────────
    if 'Jumlah_Kejadian' in df.columns:
        sorted_clusters = df.groupby('Cluster')['Jumlah_Kejadian'].mean().sort_values()
    else:
        sorted_clusters = df.groupby('Cluster').size().sort_values()

    # Urutkan ID Cluster secara fisik agar Cluster 1 = Rendah, Cluster 2 = Sedang, Cluster 3 = Tinggi
    # Ini memastikan kecocokan 100% dengan warna badge dan keterangan di UI / template
    cluster_mapping = {cluster_id: i + 1 for i, cluster_id in enumerate(sorted_clusters.index)}
    df['Cluster'] = df['Cluster'].map(cluster_mapping)

    kategori = ['Rendah', 'Sedang', 'Tinggi']
    label_map = {i + 1: kategori[i] for i in range(len(kategori))}

    df['Kategori'] = df['Cluster'].map(label_map)

    # ─────────────────────────────────────────────────────
    # BERSIHKAN KOLOM UNTUK DISPLAY
    # ─────────────────────────────────────────────────────
    full_df_dict = df.to_dict(orient='records')
    
    display_cols = [c for c in df.columns if c not in ['Hari_Numerik', 'Jam_Numerik', 'Jumlah_Kejadian', 'Cluster', 'Kategori']]
    df_display = df[display_cols + ['Kategori', 'Cluster']]

    request.session['kmeans_hasil_cluster'] = full_df_dict
    request.session['kmeans_hasil_cluster_display'] = df_display.to_dict(orient='records')
    request.session['kmeans_k'] = k
    request.session.modified = True

    show_all       = request.GET.get('show_all') == '1'
    show_all_hasil = request.GET.get('show_all_hasil') == '1'

    summary_json = request.session.get('kmeans_summary_df')
    preview_df   = pd.DataFrame()
    if summary_json:
        try:
            preview_df = pd.DataFrame(summary_json) if isinstance(summary_json, list) \
                         else pd.read_json(StringIO(summary_json), orient='records')
        except Exception:
            preview_df = pd.DataFrame()

    hasil_list = request.session.get('kmeans_hasil_cluster_display', df_display.to_dict(orient='records'))

    return render(request, 'coreapp/k-means/preprocessing.html', {
        'preview'            : (preview_df.to_dict(orient='records') if show_all
                                else preview_df.head(10).to_dict(orient='records'))
                               if not preview_df.empty else [],
        'is_full_preview'    : show_all,
        'jumlah_data_bersih' : len(preview_df) if not preview_df.empty else len(df),
        'jumlah_data_awal'   : request.session.get('kmeans_jumlah_data_asli'),
        'hasil_cluster'      : hasil_list if show_all_hasil else hasil_list[:10],
        'is_full_hasil'      : show_all_hasil,
        'k'                  : k,
    })


# ==========================================
# HALAMAN HASIL K-MEANS VIEW
# ==========================================
@login_required(login_url='login')
def hasil(request):
    data = request.session.get("kmeans_hasil_cluster")

    if not data:
        return render(request, "coreapp/k-means/hasil.html", {"belum_clustering": True})

    if isinstance(data, list):
        df = pd.DataFrame(data)
    else:
        try:
            df = pd.read_json(StringIO(data), orient='records')
        except Exception:
            df = pd.DataFrame(data)

    if df.empty:
        return render(request, "coreapp/k-means/hasil.html", {"belum_clustering": True})

    cluster_count       = df['Cluster'].value_counts().sort_index()
    cluster_labels      = [f"Cluster {i}" for i in cluster_count.index]
    cluster_values      = [int(v) for v in cluster_count.values]
    total               = sum(cluster_values)
    cluster_percentages = [round((v / total) * 100, 2) if total > 0 else 0 for v in cluster_values]

    scatter_data = []
    for _, row in df.iterrows():
        jam      = row.get('Jam_Numerik', None)
        hari     = row.get('Hari_Numerik', None)
        cluster  = row.get('Cluster', 0)
        kategori = row.get('Kategori', '')
        jumlah   = row.get('Jumlah_Kejadian', 1)
        if jam is not None and hari is not None:
            scatter_data.append({
                'x'        : int(jam),
                'y'        : float(hari),
                'cluster'  : int(cluster),
                'kategori' : str(kategori),
                'jumlah'   : int(jumlah),
            })

    jumlah_data_awal   = request.session.get('kmeans_jumlah_data_asli')
    jumlah_data_bersih = len(df)

    hasil_cluster_list = df.to_dict(orient='records')
    show_all           = request.GET.get('show_all') == '1'

    context = {
        "hasil_cluster":      hasil_cluster_list if show_all else hasil_cluster_list[:10],
        "is_full_preview":    show_all,
        "jumlah_data_bersih": jumlah_data_bersih,
        "hasil_cluster_json": json.dumps(hasil_cluster_list),
        "cluster_labels":      json.dumps(cluster_labels),
        "cluster_values":      cluster_values,
        "cluster_values_json": json.dumps(cluster_values),
        "cluster_percentages": cluster_percentages,
        "chart_data":         json.dumps(scatter_data),
        "chart_data_json":    json.dumps(scatter_data),
        "x_col_name":         "Jam (0-24)",
        "y_col_name":         "Hari (1=Senin...7=Minggu)",
        "jumlah_data_awal":    jumlah_data_awal,
        "jumlah_data_bersih":  jumlah_data_bersih,
        "elbow_data_json":     json.dumps(request.session.get('kmeans_elbow_data', [])),
    }

    return render(request, "coreapp/k-means/hasil.html", context)


# ==========================================
# REKOMENDASI KEBIJAKAN VIEW
# ==========================================
@login_required(login_url='login')
def rekomendasi_kebijakan(request):
    data = request.session.get("kmeans_hasil_cluster")
    if not data:
        return render(request, "coreapp/k-means/rekomendasi.html", {"belum_clustering": True})

    ai_data = request.session.get("kmeans_ai_recommendation_data")
    if not ai_data:
        return render(request, "coreapp/k-means/rekomendasi.html", {"belum_ai": True})

    df = pd.DataFrame(data)
    tinggi_df = df[df['Kategori'].str.lower() == 'tinggi'].sort_values(by='Jumlah_Kejadian', ascending=False)
    
    critical_hours = tinggi_df.head(10).to_dict(orient='records')
    
    total_slots = 168
    count_tinggi = len(df[df['Kategori'].str.lower() == 'tinggi'])
    count_sedang = len(df[df['Kategori'].str.lower() == 'sedang'])
    pct_tinggi = round((count_tinggi / total_slots) * 100, 1)
    
    context = {
        "critical_hours": critical_hours,
        "pct_tinggi": pct_tinggi,
        "count_tinggi": count_tinggi,
        "count_sedang": count_sedang,
        "k": request.session.get('kmeans_k', 3),
        "today": pd.Timestamp.now().strftime('%d %B %Y'),
        "ai_data": request.session.get('kmeans_ai_recommendation_data')
    }
    
    return render(request, "coreapp/k-means/rekomendasi.html", context)


# ==========================================
# AJAX: GET AI RECOMMENDATION (GEMINI) VIEW
# ==========================================
@login_required(login_url='login')
def get_ai_recommendation(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Method not allowed"}, status=405)

    data = request.session.get("kmeans_hasil_cluster")
    if not data:
        return JsonResponse({"success": False, "message": "Data cluster tidak ditemukan"}, status=400)

    df = pd.DataFrame(data)
    
    total = len(df)
    tinggi = len(df[df['Kategori'].str.lower() == 'tinggi'])
    persen = round((tinggi / total) * 100, 1)
    
    tinggi_df = df[df['Kategori'].str.lower() == 'tinggi'].sort_values(by='Jumlah_Kejadian', ascending=False)
    cluster_sample = tinggi_df.head(20).to_dict(orient='records')
    
    waktu_rawan = "Beberapa titik kritis teridentifikasi"
    if not tinggi_df.empty:
        peak = tinggi_df.iloc[0]
        waktu_rawan = f"{peak['Hari']} pukul {peak['Jam']}"

    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.integer): return int(obj)
            if isinstance(obj, np.floating): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
            return super(NpEncoder, self).default(obj)

    prompt = f"""
    Sebagai AI Ahli Keselamatan Jalan, berikan rekomendasi kebijakan berdasarkan data clustering K-Means berikut.
    
    DATA RINGKASAN:
    - Total Unit Analisis: {total} slot waktu (Hari + Jam)
    - Slot Risiko Tinggi (Cluster Tinggi): {tinggi} titik ({persen}%)
    - Titik Terkritis: {waktu_rawan}
    
    SAMPEL DATA CLUSTER TINGGI (High Risk):
    {json.dumps(cluster_sample, cls=NpEncoder)}
    
    INSTRUKSI ANALISIS:
    1. Identifikasi pola temporal (hari/jam) yang menjadi hotspot kecelakaan.
    2. Berikan matriks intervensi yang spesifik dan terukur (patroli, infrastruktur, regulasi).
    3. Targetkan pengurangan angka kecelakaan berdasarkan densitas cluster tinggi.
    
    FORMAT OUTPUT (HARUS JSON VALID MURNI):
    {{
        "ringkasan": "Analisis kritis terhadap korelasi hari/jam dan frekuensi kejadian.",
        "prioritas_tinggi": [
            {{ 
                "waktu": "Hari X Pukul Y", 
                "kejadian": "Z kejadian", 
                "tindakan": {{ 
                    "patroli": "Tindakan pengawasan spesifik", 
                    "infrastruktur": ["Perbaikan rambu/lampu", "Markah jalan"] 
                }} 
            }}
        ],
        "jadwal_patroli": [
            {{ "hari": "...", "jam": "...", "fokus": "Aspek utama yang diawasi", "unit": "X" }}
        ],
        "target_kpi": {{
            "pengurangan": "Estimasi % pengurangan jika rekomendasi dijalankan",
            "indikator": ["Key Performance Indicator 1", "KPI 2"]
        }},
        "program": {{
            "jangka_pendek": ["Langkah darurat 1 bulan"],
            "jangka_menengah": ["Pembangunan/Regulasi 6-12 bulan"]
        }},
        "catatan": "Pesan penutup strategis."
    }}
    - Bahasa Indonesia formal.
    - Tanpa penjelasan markdown di luar JSON.
    """

    try:
        ai_data = parse_ai_json(request_ai_completion(prompt, 'kmeans', timeout=30))

        request.session['kmeans_ai_recommendation_data'] = ai_data
        request.session.modified = True
        return JsonResponse({"success": True, "data": ai_data})
    except requests.exceptions.Timeout:
        return JsonResponse({"success": False, "message": "Koneksi ke provider AI timeout."}, status=504)
    except (ValueError, RuntimeError, json.JSONDecodeError) as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)
    except Exception as e:
        return JsonResponse({"success": False, "message": f"System Error: {str(e)}"}, status=500)


# ==========================================
# AJAX: GET AI DASHBOARD ANALYSIS (GEMINI) VIEW
# ==========================================
@login_required(login_url='login')
def analyze_accident_clustering(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Method not allowed"}, status=405)

    cached_analysis = request.session.get('kmeans_ai_dashboard_analysis')
    if cached_analysis and request.POST.get('force') != '1':
        return JsonResponse({"success": True, "analysis": cached_analysis})

    data = request.session.get("kmeans_hasil_cluster")
    if not data:
        return JsonResponse({"success": False, "message": "Data cluster tidak ditemukan"}, status=400)

    df = pd.DataFrame(data)
    total_incidents = int(df['Jumlah_Kejadian'].sum())
    total_slots = len(df)

    # 1. Agregasi Bar Chart
    clusters = []
    for kat in ['Rendah', 'Sedang', 'Tinggi']:
        count = int(df[df['Kategori'] == kat]['Jumlah_Kejadian'].sum())
        pct = round((count / total_incidents) * 100, 1) if total_incidents > 0 else 0
        clusters.append({"name": kat, "count": count, "percentage": pct})

    # 2. Agregasi Scatter Plot (Hotspots)
    hotspots = df.sort_values('Jumlah_Kejadian', ascending=False).head(5)
    hotspot_list = []
    for _, row in hotspots.iterrows():
        hotspot_list.append({
            "day": row['Hari'], "hour": row['Jam'], 
            "count": int(row['Jumlah_Kejadian']), "cluster": row['Kategori']
        })

    # 3. Agregasi Line Chart (Peaks & Transitions)
    hourly_avg = df.groupby('Jam_Numerik')['Jumlah_Kejadian'].mean()
    peaks = []
    if not hourly_avg.empty:
        max_idx = hourly_avg.idxmax()
        peaks.append({"label": "Puncak", "hour": f"{int(max_idx):02d}:00", "val": round(float(hourly_avg[max_idx]), 1)})

    # Construct Prompt
    class NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.integer): return int(obj)
            if isinstance(obj, np.floating): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
            return super(NpEncoder, self).default(obj)

    prompt = f"""
    Analisis data clustering K-Means kecelakaan berikut (Total {total_incidents} kejadian):
 
    1. DISTRIBUSI CLUSTER:
    {json.dumps(clusters, cls=NpEncoder)}
 
    2. HOTSPOTS (Titik Tertinggi):
    {json.dumps(hotspot_list, cls=NpEncoder)}
 
    3. TREN 24 JAM (Rata-rata Kejadian):
    {hourly_avg.to_dict()}
 
    INSTRUKSI:
    Berikan analisis untuk 3 chart (Bar Chart, Scatter Plot, Line Chart) dalam format JSON murni:
    {{
      "barChart": {{ "summary": "...", "insights": [{{ "text": "...", "dataPoint": "...", "emphasis": "high/medium/low" }}] }},
      "scatterPlot": {{ "summary": "...", "insights": [...] }},
      "lineChart": {{ "summary": "...", "insights": [...] }}
    }}
    - Summary 1-2 kalimat.
    - 3-4 insight per chart dengan angka spesifik.
    - Bahasa Indonesia profesional.
    - Tanpa saran/rekomendasi.
    """

    try:
        analysis_data = parse_ai_json(request_ai_completion(prompt, 'kmeans', timeout=30))

        request.session['kmeans_ai_dashboard_analysis'] = analysis_data
        request.session.modified = True

        return JsonResponse({"success": True, "analysis": analysis_data})
    except requests.exceptions.Timeout:
        return JsonResponse({"success": False, "message": "Koneksi ke provider AI timeout."}, status=504)
    except (ValueError, RuntimeError, json.JSONDecodeError) as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)
    except Exception as e:
        return JsonResponse({"success": False, "message": f"System Error: {str(e)}"}, status=500)


# ==========================================
# CONFIGURATION MANAGEMENT VIEW
# ==========================================
@login_required(login_url='login')
def save_ai_config(request):
    if request.method == "POST":
        tipe = request.POST.get('tipe', 'kmeans')
        api_key = request.POST.get('api_key')
        provider = request.POST.get('provider', 'gemini')
        if provider not in {'gemini', 'groq'}:
            return JsonResponse({"success": False, "message": "Provider AI tidak valid."}, status=400)
        
        config, created = AIConfig.objects.get_or_create(tipe=tipe)
        config.provider = provider
        config.api_key = api_key
        config.save()
        
        return JsonResponse({"success": True, "message": "API Key berhasil disimpan"})
    
    return JsonResponse({"success": False, "message": "Invalid request"}, status=400)


# ==========================================
# UNUSED LEGACY K-MEANS VIEWS
# ==========================================
@login_required(login_url='login')
def kmeans_data(request):
    return render(request, 'coreapp/kmeans/data.html')

@login_required(login_url='login')
def kmeans_proses(request):
    return render(request, 'coreapp/kmeans/proses.html')

@login_required(login_url='login')
def kmeans_hasil(request):
    return render(request, 'coreapp/kmeans/hasil.html')