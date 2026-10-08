import pandas as pd
import numpy as np
import re
import os
import json
import requests
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from .models import AIConfig, AhcPreprosesing
from .ai_utils import parse_ai_json, request_ai_completion
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score
import logging

logger = logging.getLogger(__name__)
from sklearn.decomposition import PCA
from scipy.cluster.hierarchy import linkage
import plotly.express as px
import plotly.graph_objects as go
from plotly.figure_factory import create_dendrogram


def _save_uploaded_ahc_data(df):
    """Simpan baris file upload AHC ke tabel khusus sebelum transformasi."""
    from decimal import Decimal, InvalidOperation
    from .models import AhcPreprosesing

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
            digits = re.sub(r'[^0-9.-]', '', str(raw_value))
            return Decimal(digits or '0')
        except (InvalidOperation, ValueError):
            return Decimal('0')

    records = []
    for _, row in df.iterrows():
        age = pd.to_numeric(value(row, 'umur', 0), errors='coerce')
        records.append(AhcPreprosesing(
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
        AhcPreprosesing.objects.bulk_create(records, batch_size=1000)

# ================================
# HALAMAN DATA
# ================================
@login_required(login_url='login')
def ahc_data(request):
    all_data = AhcPreprosesing.objects.all().order_by('-tanggal', '-jam')
    total_count = all_data.count()
    
    # Paginasi 20 item per halaman
    paginator = Paginator(all_data, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'data_list': page_obj,
        'total_data': total_count,
    }
    return render(request, 'coreapp/ahc/data.html', context)

# ================================
# HALAMAN PROSES (UI)
# ================================
@login_required(login_url='login')
def ahc_proses(request):
    context = {}
    summary_df = request.session.get('ahc_summary_df')
    jumlah_data_asli = request.session.get('ahc_jumlah_data_asli')
    hasil_cluster = request.session.get('ahc_hasil_cluster')
    summary_cluster = request.session.get('ahc_summary_cluster')
    jumlah_cluster = request.session.get('ahc_jumlah_cluster')

    if summary_df:
        context['preview'] = summary_df
        context['jumlah_data'] = request.session.get('ahc_jumlah_data', len(summary_df))
        context['jumlah_data_asli'] = jumlah_data_asli

    if hasil_cluster:
        context['hasil_cluster'] = hasil_cluster
        context['summary_cluster'] = summary_cluster
        context['jumlah_cluster'] = jumlah_cluster

    return render(request, 'coreapp/ahc/proses.html', context)

# ================================
# PREPROCESSING DATA AHC
# ================================
@login_required(login_url='login')
def preprocessing_data(request):
    context = {}
    use_db = request.GET.get('use_db') == '1'
    
    if request.method == "POST" or use_db:
        
        keys_to_clear = [
            'ahc_hasil_cluster', 'ahc_summary_cluster', 'ahc_jumlah_cluster', 'ahc_jumlah_data', 
            'ahc_silhouette_score', 'ahc_X_scaled', 'ahc_summary_df', 'ahc_jumlah_data_asli', 
            'ai_explain_cache', 'ahc_ai_rekomendasi', 'ai_context_data',
            'ai_pca', 'ai_dendrogram', 'ai_bar', 'ai_faktor', 'ai_umur',
            'ahc_uploaded_file_name'
        ]
        for key in keys_to_clear:
            request.session.pop(key, None)

        df = None
        if use_db:
            data_db = AhcPreprosesing.objects.all().values()
            if not data_db:
                messages.error(request, "Data di database masih kosong.")
                return redirect('ahc_proses')
            df = pd.DataFrame(list(data_db))
            # Map database fields to standard names
            df = df.rename(columns={
                'tkp': 'TKP', 'penyebab': 'Penyebab', 'hari': 'Hari',
                'tanggal': 'Tanggal', 'jam': 'Jam', 'umur': 'Umur',
                'jenis_kendaraan': 'Jenis Kendaraan', 'tipe_kendaraan': 'Tipe Kendaraan',
                'kerugian_material': 'Kerugian Material'
            })
            request.session['ahc_uploaded_file_name'] = "Database AHC"
        else:
            file = request.FILES.get('file')
            if file:
                request.session['ahc_uploaded_file_name'] = file.name
                df = pd.read_excel(file)
                _save_uploaded_ahc_data(df)

        if df is not None:
            df.columns = [str(c).strip() for c in df.columns]

            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].apply(lambda x: " ".join(str(x).split()) if pd.notnull(x) else "")
                    df[col] = df[col].str.title()

            request.session['ahc_jumlah_data_asli'] = len(df)
            df.replace(['-', 'Nan', 'nan'], np.nan, inplace=True)

            if 'Umur' in df.columns:
                df['Umur'] = pd.to_numeric(df['Umur'], errors='coerce').fillna(0).astype(int)
                df = df[df['Umur'] > 0]

            def parse_kerugian(val):
                if pd.isna(val) or val == 'None': return 0
                nums = re.findall(r'\d+', str(val))
                return int("".join(nums)) if nums else 0

            if 'Kerugian Material' in df.columns:
                df['kerugian_numeric'] = df['Kerugian Material'].apply(parse_kerugian)
            else:
                df['kerugian_numeric'] = 0

            df['Penyebab_clean'] = df['Penyebab'].astype(str).str.lower()
            df['faktor_kelalaian'], df['faktor_pelanggaran'], df['faktor_teknis'] = 0, 0, 0

            kelalaian_keys = ['konsentrasi', 'mengantuk', 'hp', 'kecepatan', 'mengerem', 'oleng', 'menguasai']
            pelanggaran_keys = ['sein', 'apill', 'marka', 'arus', 'mendahului', 'jalur', 'jarak']
            teknis_keys = ['lubang', 'ban', 'rem', 'penerangan', 'speed boom', 'pintu', 'mundur']

            for i, row in df.iterrows():
                penyebab = row['Penyebab_clean']
                if any(k in penyebab for k in kelalaian_keys): df.at[i, 'faktor_kelalaian'] = 1
                if any(k in penyebab for k in pelanggaran_keys): df.at[i, 'faktor_pelanggaran'] = 1
                if any(k in penyebab for k in teknis_keys): df.at[i, 'faktor_teknis'] = 1
                if df.at[i, 'faktor_kelalaian'] == 0 and df.at[i, 'faktor_pelanggaran'] == 0 and df.at[i, 'faktor_teknis'] == 0:
                    df.at[i, 'faktor_kelalaian'] = 1

            def get_sesi_waktu(jam):
                try: h = int(str(jam).replace('.', ':').split(':')[0])
                except: return 1
                if 0 <= h < 6: return 0
                elif 6 <= h < 12: return 1
                elif 12 <= h < 18: return 2
                else: return 3

            if 'Jam' in df.columns: df['sesi_waktu_enc'] = df['Jam'].apply(get_sesi_waktu)
            else: df['sesi_waktu_enc'] = 1

            if 'Tanggal' in df.columns:
                try:
                    df['Tanggal_dt'] = pd.to_datetime(df['Tanggal'])
                    df['jenis_hari'] = df['Tanggal_dt'].dt.dayofweek.apply(lambda x: 1 if x >= 5 else 0)
                except: df['jenis_hari'] = 0
            else: df['jenis_hari'] = 0

            def encode_kendaraan(j):
                j = str(j).lower()
                if 'motor' in j: return 0
                if 'mobil' in j: return 1
                return 2

            if 'Jenis Kendaraan' in df.columns: df['jenis_kendaraan_enc'] = df['Jenis Kendaraan'].apply(encode_kendaraan)
            else: df['jenis_kendaraan_enc'] = 0

            features = ['Umur', 'faktor_kelalaian', 'faktor_pelanggaran', 'faktor_teknis', 
                        'sesi_waktu_enc', 'jenis_hari', 'jenis_kendaraan_enc']
            fitur_clustering = df[features].copy()
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(fitur_clustering)

            # Simpan ke session - Gunakan to_json lalu loads agar aman dari tipe data Timestamp/Numpy
            request.session['ahc_summary_df'] = json.loads(df.head(100).to_json(orient='records'))
            request.session['ahc_X_scaled'] = X_scaled.tolist()
            request.session['ahc_jumlah_data'] = len(df)
            request.session['ahc_full_features'] = json.loads(fitur_clustering.to_json(orient='records'))
            request.session.modified = True
            return redirect('ahc_proses')
    return render(request, 'coreapp/ahc/proses.html', context)

# ================================
# FUNGSI UNTUK MENENTUKAN K TERBAIK
# ================================
def find_best_cluster(X, max_k=5):
    best_k, best_score = 2, -1
    for k in range(2, max_k + 1):
        model = AgglomerativeClustering(n_clusters=k, linkage='ward')
        labels = model.fit_predict(X)
        score = silhouette_score(X, labels)
        if score > best_score: best_score, best_k = score, k
    return best_k

# ================================
# PROSES CLUSTERING AHC (LOGIC)
# ================================
@login_required(login_url='login')
def proses_ahc(request):
    X_scaled, full_features = request.session.get('ahc_X_scaled'), request.session.get('ahc_full_features')
    if not X_scaled or not full_features: return render(request, 'coreapp/ahc/proses.html', 
                                                        {"error": "Silakan lakukan preprocessing terlebih dahulu."})

    X_scaled, df = np.array(X_scaled), pd.DataFrame(full_features)
    n_cluster_req = request.GET.get('cluster')
    n_cluster = int(n_cluster_req) if n_cluster_req and n_cluster_req.isdigit() else find_best_cluster(X_scaled, max_k=5)

    model = AgglomerativeClustering(n_clusters=n_cluster, linkage='ward')
    labels = model.fit_predict(X_scaled)
    sil_score = round(float(silhouette_score(X_scaled, labels)), 4)

    pca = PCA(n_components=2)
    X_pca = pca.fit_transform(X_scaled)
    df_pca = df.copy()
    df_pca['PC1'], df_pca['PC2'], df_pca['Cluster'] = X_pca[:, 0], X_pca[:, 1], labels + 1

    fig_scatter = px.scatter(df_pca, x='PC1', y='PC2', color=df_pca['Cluster'].astype(str), 
    title='Visualisasi Cluster (PCA Projection)', labels={'color': 'Cluster'})
    scatter_html = fig_scatter.to_html(full_html=False)

    df['Cluster'] = labels + 1
    cluster_counts = df['Cluster'].value_counts().sort_index()
    
    # 3. Boxplot Umur per Cluster
    df_box = df.copy()
    df_box['Cluster_Name'] = 'Cluster ' + df_box['Cluster'].astype(str)
    fig_box = px.box(df_box, x="Cluster_Name", y="Umur", color="Cluster_Name", 
                     title="Distribusi Umur per Klaster", 
                     labels={"Cluster_Name": "Klaster", "Umur": "Umur (Tahun)"},
                     points="outliers")
    fig_box.update_yaxes(range=[0, 90])
    boxplot_html = fig_box.to_html(full_html=False)

    Z = linkage(X_scaled, method='ward')
    threshold = 0.7 * Z[:, 2].max()
    # Gunakan Umur sebagai label sumbu X
    labels_umur = df['Umur'].astype(str).tolist()
    fig_dendro = create_dendrogram(X_scaled, linkagefun=lambda x: Z, color_threshold=threshold, labels=labels_umur)
    x_min, x_max = min([min(t['x']) for t in fig_dendro['data'] if 'x' in t]), max([max(t['x']) for t in fig_dendro['data'] if 'x' in t])
    fig_dendro.add_trace(go.Scatter(x=[x_min, x_max], y=[threshold, threshold], mode='lines', line=dict(color='red', width=3, dash='dash'), name='Cut-off Line'))
    fig_dendro.update_layout(title="Dendrogram Hierarchical Clustering", width=1000, height=500)
    dendrogram_html = fig_dendro.to_html(full_html=False)

    summary = []
    faktor_cols = ["faktor_kelalaian", "faktor_pelanggaran", "faktor_teknis"]
    waktu_map = {0: "Dini Hari", 1: "Pagi", 2: "Siang/Sore", 3: "Malam"}
    for cluster_id in sorted(df['Cluster'].unique()):
        c_df = df[df['Cluster'] == cluster_id]
        f_sums = c_df[faktor_cols].sum()
        summary.append({
            "cluster": int(cluster_id), "jumlah": len(c_df), "persentase": round((len(c_df) / len(df)) * 100, 2),
            "rata_umur": round(c_df['Umur'].mean(), 1), "faktor_dominan": f_sums.idxmax().replace('faktor_', '').title() if f_sums.max() > 0 else "N/A",
            "waktu_dominan": waktu_map.get(c_df['sesi_waktu_enc'].mode()[0], "N/A"), "hari_dominan": "Weekend" if c_df['jenis_hari'].mode()[0] == 1 else "Weekday"
        })

    # Pastikan data serializable
    hasil_cluster_serializable = json.loads(df.to_json(orient='records'))
    request.session.update({
        'ahc_hasil_cluster': hasil_cluster_serializable, 
        'ahc_summary_cluster': summary, 
        'ahc_jumlah_cluster': n_cluster, 
        'ahc_silhouette_score': sil_score, 
        'ahc_dendrogram_html': dendrogram_html, 
        'ahc_scatter_html': scatter_html, 
        'ahc_boxplot_html': boxplot_html
    })
    
    # Bersihkan cache AI lama & Fallback lama karena data sudah berubah total
    keys_to_clear_ai = [
        'ai_explain_cache', 'ahc_ai_rekomendasi', 'ai_context_data',
        'ai_pca', 'ai_dendrogram', 'ai_boxplot', 'ai_faktor', 'ai_umur'
    ]
    for key in keys_to_clear_ai:
        request.session.pop(key, None)
    
    request.session.modified = True
    request.session.save() # Pastikan tersimpan sebelum redirect
    
    return redirect('ahc_hasil')

# ================================
# HASIL AHC
# ================================
@login_required(login_url='login')
@never_cache
def ahc_hasil(request):
    hasil_cluster = request.session.get('ahc_hasil_cluster', [])
    df = pd.DataFrame(hasil_cluster)
    summary_cluster = request.session.get('ahc_summary_cluster', [])
    jumlah_cluster, jumlah_data, silhouette = request.session.get('ahc_jumlah_cluster'), request.session.get('ahc_jumlah_data'), request.session.get('ahc_silhouette_score')
    scatter_html, dendrogram_html, boxplot_html = request.session.get('ahc_scatter_html'), request.session.get('ahc_dendrogram_html'), request.session.get('ahc_boxplot_html')

    if not summary_cluster: return render(request, 'coreapp/ahc/hasil.html', {"belum_clustering": True})
    ai_global = generate_ai_insight(summary_cluster, silhouette)
    faktor_total = {pretty: int(df[raw].sum()) for raw, pretty in {"faktor_kelalaian": "Kelalaian", "faktor_pelanggaran": "Pelanggaran", "faktor_teknis": "Teknis"}.items() if raw in df.columns}
    faktor_labels, faktor_values = list(faktor_total.keys()), list(faktor_total.values())

    def kategori_umur(u):
        if u <= 11: return "5-11 (Kanak-kanak)"
        elif u <= 16: return "12-16 (Remaja Awal)"
        elif u <= 25: return "17-25 (Remaja Akhir)"
        elif u <= 35: return "26-35 (Dewasa Awal)"
        elif u <= 45: return "36-45 (Dewasa Akhir)"
        elif u <= 55: return "46-55 (Lansia Awal)"
        elif u <= 65: return "56-65 (Lansia Akhir)"
        else: return "66-90 (Manula)"

    df['Kelompok Umur'] = df['Umur'].apply(kategori_umur)
    grouped = df.groupby('Kelompok Umur')[["faktor_kelalaian", "faktor_pelanggaran", "faktor_teknis"]].sum().reset_index()
    umur_labels, f_kelalaian, f_pelanggaran, f_teknis = grouped['Kelompok Umur'].tolist(), grouped['faktor_kelalaian'].tolist(), grouped['faktor_pelanggaran'].tolist(), grouped['faktor_teknis'].tolist()
    total_per_umur = [f_kelalaian[i] + f_pelanggaran[i] + f_teknis[i] for i in range(len(umur_labels))]
    max_u_idx = total_per_umur.index(max(total_per_umur))
    f_list = [("Kelalaian", f_kelalaian[max_u_idx]), ("Pelanggaran", f_pelanggaran[max_u_idx]), ("Teknis", f_teknis[max_u_idx])]
    
    max_idx = faktor_values.index(max(faktor_values))

    # Data untuk Chart Distribusi Populasi
    cluster_counts_dict = df['Cluster'].value_counts().sort_index().to_dict()
    cluster_labels = [f"Cluster {c}" for c in cluster_counts_dict.keys()]
    cluster_counts = list(cluster_counts_dict.values())

    # Data untuk Modal Detail
    waktu_map = {0: "Dini Hari", 1: "Pagi", 2: "Siang/Sore", 3: "Malam"}
    cluster_detail = {}
    for cluster_id in cluster_counts_dict.keys():
        c_df = df[df['Cluster'] == cluster_id]
        details = []
        for _, row in c_df.iterrows():
            factor = "N/A"
            if row.get('faktor_kelalaian'): factor = "Kelalaian"
            elif row.get('faktor_pelanggaran'): factor = "Pelanggaran"
            elif row.get('faktor_teknis'): factor = "Teknis"
            details.append(f"Umur: {row['Umur']} | Faktor: {factor} | Waktu: {waktu_map.get(row['sesi_waktu_enc'], 'N/A')}")
        cluster_detail[f"Cluster {cluster_id}"] = details

    # ==========================================
    # ANALISIS DINAMIS TIAP DIAGRAM
    # ==========================================
    # ==========================================
    # ANALISIS DINAMIS TIAP DIAGRAM (Narrative Style)
    # ==========================================

    # 1. Analisis PCA (Dynamic Position & Density)
    X_scaled = request.session.get('ahc_X_scaled')
    ai_pca = ""
    if X_scaled:
        X_scaled_arr = np.array(X_scaled)
        pca_engine = PCA(n_components=2)
        X_pca_coords = pca_engine.fit_transform(X_scaled_arr)
        
        pca_df = pd.DataFrame(X_pca_coords, columns=['PC1', 'PC2'])
        pca_df['Cluster'] = df['Cluster'].values
        
        pos_stats = []
        for c_id in sorted(pca_df['Cluster'].unique()):
            c_data = pca_df[pca_df['Cluster'] == c_id]
            pos_stats.append({
                'id': int(c_id),
                'pc1': c_data['PC1'].mean(),
                'pc2': c_data['PC2'].mean(),
                'std': (c_data['PC1'].std() + c_data['PC2'].std()) / 2,
                'count': len(c_data)
            })
            
        # Tentukan posisi relatif
        desc_parts = []
        for s in pos_stats:
            pos_h = "sisi kanan" if s['pc1'] > 0 else "sisi kiri"
            pos_v = "bagian atas" if s['pc2'] > 0 else "bagian bawah"
            density = "cukup rapat" if s['std'] < 1.0 else "cukup tersebar"
            
            part = f"<b>Cluster {s['id']}</b> berada di {pos_h} {pos_v} dengan pola yang {density}, menunjukkan bahwa karakteristik dalam kelompok ini {'relatif mirip satu sama lain' if s['std'] < 1.0 else 'memiliki variasi yang cukup beragam'}."
            desc_parts.append(part)
            
        ai_pca = f"""
        <p>Dari visualisasi PCA di atas, terlihat bahwa data terbagi menjadi <b>{jumlah_cluster} kelompok</b> dengan sebaran spasial yang mencerminkan perbedaan karakteristik yang unik:</p>
        <div class="mt-3 space-y-2">
            {''.join([f'<p>{p}</p>' for p in desc_parts])}
        </div>
        <p class="mt-4 text-blue-900 font-bold uppercase tracking-widest text-[10px]">Beberapa poin penting dalam diagram tersebut:</p>
        <ul class="list-disc ml-5 mt-2 space-y-1">
            <li>Jarak antar klaster yang terpisah menandakan perbedaan pola kejadian kecelakaan yang jelas antar kelompok.</li>
            <li>Klaster dengan sebaran padat menandakan konsistensi perilaku atau faktor penyebab dalam kelompok tersebut.</li>
            <li>Posisi klaster yang terisolasi jauh dari kelompok lain menandakan kasus dengan profil risiko yang sangat spesifik atau jarang terjadi.</li>
        </ul>
        """
    else:
        ai_pca = "<p>Data PCA tidak tersedia untuk analisis mendalam.</p>"

    # 2. Analisis Dendrogram (Detailed Narrative)
    ai_dendrogram = f"""
    <p>Visualisasi struktur pohon atau dendrogram ini menggambarkan proses pengelompokan data secara hierarkis berdasarkan tingkat kemiripan antar kejadian kecelakaan. Sumbu vertikal (Y) merepresentasikan jarak atau perbedaan; semakin rendah posisi penggabungan dua cabang, semakin tinggi tingkat kemiripan karakteristik data di dalamnya.</p>
    
    <p class="mt-2">Dalam diagram ini, terlihat bahwa mayoritas data bergabung pada level jarak yang cukup rendah (bagian bawah), yang mengindikasikan adanya kesamaan pola yang kuat pada sebagian besar kasus. Namun, terdapat beberapa cabang utama yang baru menyatu pada ketinggian yang lebih signifikan, menandakan adanya perbedaan karakteristik yang cukup kontras antar kelompok besar tersebut.</p>

    <p class="mt-2">Garis merah putus-putus (cut-off line) diletakkan secara otomatis sebagai ambang batas untuk menentukan jumlah kelompok paling representatif. Berdasarkan posisi garis tersebut, data secara optimal terbagi menjadi <b>{jumlah_cluster} klaster utama</b>.</p>

    <p class="mt-4 text-blue-900 font-bold uppercase tracking-widest text-[10px]">Hal penting yang perlu diperhatikan:</p>
    <ul class="list-disc ml-5 mt-2 space-y-1">
        <li><b>Penggabungan di level bawah</b> menandakan adanya konsistensi data yang tinggi dalam pembentukan sub-cluster.</li>
        <li><b>Celah antar cabang utama</b> yang terlihat jelas menunjukkan bahwa pola pengelompokan (clustering) ini memiliki struktur yang kuat.</li>
        <li><b>Garis ambang batas (red line)</b> berfungsi sebagai penentu jumlah klaster (K={jumlah_cluster}) yang paling seimbang untuk dianalisis lebih lanjut.</li>
    </ul>
    """

    # 3. Analisis Boxplot Umur
    ai_boxplot = f"""
    <p>Grafik boxplot ini memvisualisasikan sebaran umur di setiap klaster, yang membantu memvalidasi tingkat homogenitas data. Kotak (box) yang sempit menandakan usia kelompok yang homogen, sementara kotak lebar menunjukkan variasi usia yang tinggi.</p>
    <p class="mt-2">Selain itu, garis median di tengah kotak memperlihatkan profil umur dominan tiap kelompok. Adanya titik-titik di luar rentang (outlier) menandakan anomali umur yang mungkin memerlukan perhatian khusus dibandingkan mayoritas kejadian pada klaster tersebut.</p>
    """

    # 4. Analisis Faktor (Global)
    total_kasus = sum(faktor_values)
    pct_max = round((max(faktor_values) / total_kasus) * 100, 1) if total_kasus > 0 else 0
    ai_faktor = f"""
    <p>Analisis faktor penyebab secara menyeluruh memberikan gambaran mengenai akar masalah utama kecelakaan di lapangan. Terlihat bahwa mayoritas kejadian di wilayah ini dipicu oleh aspek <b>{faktor_labels[max_idx]}</b> yang mendominasi sebesar <b>{pct_max}%</b> dari total data.</p>
    <p class="mt-2">Temuan ini mempertegas bahwa strategi pencegahan taktis, baik dalam bentuk sosialisasi maupun penegakan hukum, harus difokuskan secara mendalam pada penanganan masalah {faktor_labels[max_idx].lower()} tersebut.</p>
    """

    # 5. Analisis Umur vs Faktor (Data-Focused Narrative)
    max_u_label = umur_labels[max_u_idx]
    max_u_total = total_per_umur[max_u_idx]
    max_u_factor = max(f_list, key=lambda x: x[1])[0]
    
    ai_umur = f"""
    <p>Grafik ini memvisualisasikan korelasi antara kelompok usia pengendara dengan faktor-faktor penyebab kecelakaan yang terjadi. Melalui distribusi bar yang bertumpuk, kita dapat melihat bagaimana profil risiko bergeser di setiap tahapan usia produktif hingga lansia.</p>
    
    <p class="mt-2">Berdasarkan data yang disajikan, terlihat konsentrasi kasus yang sangat tinggi pada kelompok usia <b>{max_u_label}</b> dengan total mencapai <b>{max_u_total} kejadian</b>. Jika dianalisis lebih dalam, faktor <b>{max_u_factor}</b> menjadi variabel yang paling dominan mempengaruhi angka kecelakaan pada rentang usia tersebut dibandingkan faktor lainnya.</p>

    <p class="mt-2">Selain itu, diagram juga memperlihatkan tren di kelompok usia lain, di mana terdapat perbedaan proporsi antara faktor kelalaian, pelanggaran, dan teknis. Hal ini menunjukkan bahwa karakteristik penyebab kecelakaan memiliki keterkaitan yang kuat dengan profil demografi pengendara di wilayah Kota Madiun.</p>

    <p class="mt-4 text-blue-900 font-bold uppercase tracking-widest text-[10px]">Kesimpulan Utama:</p>
    <ul class="list-disc ml-5 mt-2 space-y-1">
        <li>Angka kecelakaan mencapai puncaknya pada kelompok <b>{max_u_label}</b>.</li>
        <li>Faktor <b>{max_u_factor}</b> adalah kontributor terbesar dalam data statistik pada kelompok usia paling rentan.</li>
        <li>Terdapat variasi komposisi faktor penyebab di setiap kategori umur, yang mencerminkan perbedaan pola perilaku atau kondisi kendaraan antar kelompok usia.</li>
    </ul>
    """

    # Simpan analisis standar ke session sebagai cadangan (fallback)
    request.session['ahc_ai_pca'] = ai_pca
    request.session['ahc_ai_dendrogram'] = ai_dendrogram
    request.session['ahc_ai_boxplot'] = ai_boxplot
    request.session['ahc_ai_faktor'] = ai_faktor
    request.session['ahc_ai_umur'] = ai_umur

    request.session['ahc_ai_context_data'] = {
        "max_faktor": faktor_labels[max_idx],
        "max_faktor_pct": pct_max,
        "max_umur_label": max_u_label,
        "max_umur_total": int(max_u_total),
        "max_umur_faktor": max_u_factor
    }

    request.session.modified = True
    request.session.save()

    return render(request, 'coreapp/ahc/hasil.html', {
        "hasil_cluster": hasil_cluster, "summary_cluster": summary_cluster, "jumlah_cluster": jumlah_cluster, 
        "jumlah_data": jumlah_data, "total_kejadian": jumlah_data, "silhouette_score": silhouette,
        "ahc_scatter_html": scatter_html, "ahc_dendrogram_html": dendrogram_html, "ahc_boxplot_html": boxplot_html,
        "scatter_html": scatter_html, "dendrogram_html": dendrogram_html, "boxplot_html": boxplot_html,
        "faktor_labels": faktor_labels, "faktor_values": faktor_values, "umur_labels": umur_labels,
        "cluster_labels": cluster_labels, "cluster_counts": cluster_counts, "cluster_detail": cluster_detail,
        "faktor_kelalaian": f_kelalaian, "faktor_pelanggaran": f_pelanggaran, "faktor_teknis": f_teknis, 
        "ai_faktor": ai_faktor, "ai_umur": ai_umur, "ai_global": ai_global,
        "ai_boxplot": ai_boxplot, "ai_pca": ai_pca, "ai_dendrogram": ai_dendrogram,
        "ahc_ai_explain_cache": request.session.get('ahc_ai_explain_cache')
    })

# ================================
# RESET AHC
# ================================
@login_required(login_url='login')
def reset_ahc(request):
    keys_to_clear = [
        'ahc_hasil_cluster', 'ahc_summary_cluster', 'ahc_jumlah_cluster', 'ahc_jumlah_data',
        'ahc_silhouette_score', 'ahc_X_scaled', 'ahc_summary_df', 'ahc_full_features',
        'ahc_ai_explain_cache', 'ahc_ai_rekomendasi', 'ahc_ai_context_data',
        'ahc_uploaded_file_name', 'ahc_ai_pca', 'ahc_ai_dendrogram', 'ahc_ai_boxplot',
        'ahc_ai_faktor', 'ahc_ai_umur', 'ahc_jumlah_data_asli', 'ahc_scatter_html',
        'ahc_dendrogram_html', 'ahc_boxplot_html'
    ]
    for k in keys_to_clear:
        request.session.pop(k, None)
    request.session.modified = True
    return redirect('ahc_proses')

# ================================
# AI ENGINE
# ================================
def generate_ai_insight(summary_cluster, silhouette):
    if not summary_cluster: return "Belum ada data untuk dianalisis."
    
    max_c = max(summary_cluster, key=lambda x: x['jumlah'])
    
    # Grid info
    insight = f"""
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
        <div class="bg-white/60 p-4 rounded-xl border border-blue-100">
            <p class="text-[10px] text-blue-600 uppercase tracking-widest font-black mb-1">Klaster Dominan</p>
            <p class="text-lg font-bold text-blue-900">Klaster {max_c['cluster']} ({max_c['jumlah']} Kejadian)</p>
        </div>
        <div class="bg-white/60 p-4 rounded-xl border border-blue-100">
            <p class="text-[10px] text-blue-600 uppercase tracking-widest font-black mb-1">Validitas (Silhouette)</p>
            <p class="text-lg font-bold text-blue-900">{silhouette if silhouette else '-'}</p>
        </div>
    </div>

    <div class="space-y-4">
    """

    for s in summary_cluster:
        insight += f"""
        <div class="flex items-start gap-3 group">
            <div class="flex-shrink-0 mt-1">
                <i class="fas fa-check-circle text-blue-500"></i>
            </div>
            <div class="text-sm text-blue-900 leading-relaxed">
                <span class="font-black">Klaster {s['cluster']}</span>: Didominasi faktor <b>{s['faktor_dominan']}</b> (korban rata-rata <b>{s['rata_umur']} Thn</b>). 
                Pola kejadian pada <b>{s['waktu_dominan']}</b> di hari <b>{s['hari_dominan']}</b>.
            </div>
        </div>
        """
    
    # Rekomendasi
    rec = "Tingkatkan rambu-rambu peringatan."
    if max_c['faktor_dominan'] == "Kelalaian" and max_c['rata_umur'] < 30: 
        rec = "Prioritaskan edukasi keselamatan berkendara di institusi pendidikan dan perketat pengawasan SIM bagi pengendara usia muda."
    elif max_c['faktor_dominan'] == "Pelanggaran" and max_c['waktu_dominan'] == "Malam": 
        rec = "Tambah intensitas patroli kepolisian pada jam malam dan optimalkan sistem ETLE di titik rawan klaster ini."
    elif max_c['faktor_dominan'] == "Teknis": 
        rec = "Perketat pengawasan uji berkala kendaraan (KIR) untuk memastikan kelaikan teknis kendaraan di jalan raya."

    insight += f"""
    </div>

    <div class="mt-8 pt-6 border-t border-blue-100">
        <p class="text-[10px] text-blue-600 uppercase tracking-widest font-black mb-2">Rekomendasi Taktis</p>
        <div class="bg-blue-600 text-white p-4 rounded-xl shadow-lg shadow-blue-200/50 italic text-sm">
            "{rec}"
        </div>
    </div>
    """
    return insight

# ================================
# AI DIAGRAM EXPLAINER (GEMINI)
# ================================
@login_required(login_url='login')
def ahc_ai_explain(request):
    # 1. Cek Cache (Pola Final YOLA)
    force = request.POST.get('force') == '1'
    cached = request.session.get('ahc_ai_explain_cache')
    
    if cached and not force:
        return JsonResponse({"status": "ok", "data": cached, "source": "cache"})

    # 2. Ambil Data
    hasil_cluster = request.session.get('ahc_hasil_cluster')
    summary_cluster = request.session.get('ahc_summary_cluster')
    silhouette = request.session.get('ahc_silhouette_score')
    X_scaled = request.session.get('ahc_X_scaled')

    if not hasil_cluster or not summary_cluster or X_scaled is None:
        return JsonResponse({"status": "error", "message": "Data clustering belum tersedia."}, status=400)

    try:
        df = pd.DataFrame(hasil_cluster)
        X_scaled_arr = np.array(X_scaled)
        
        # Meta Info
        sil_kat = "Kurang"
        if silhouette >= 0.7: sil_kat = "Sangat Baik"
        elif silhouette >= 0.5: sil_kat = "Baik"
        elif silhouette >= 0.25: sil_kat = "Cukup"

        # PCA Stats
        pca_engine = PCA(n_components=2)
        X_pca_coords = pca_engine.fit_transform(X_scaled_arr)
        evr = [round(float(v), 2) for v in pca_engine.explained_variance_ratio_]
        
        pca_df = pd.DataFrame(X_pca_coords, columns=['PC1', 'PC2'])
        pca_df['Cluster'] = df['Cluster'].values
        
        pca_positions = []
        centroids = {}
        for c_id in sorted(pca_df['Cluster'].unique()):
            c_data = pca_df[pca_df['Cluster'] == c_id]
            c_id_int = int(c_id)
            m1, m2 = c_data['PC1'].mean(), c_data['PC2'].mean()
            s1, s2 = c_data['PC1'].std(), c_data['PC2'].std()
            centroids[c_id_int] = (m1, m2)
            pca_positions.append({
                "id": c_id_int,
                "pc1_mean": round(m1, 2), "pc2_mean": round(m2, 2),
                "std_pc1": round(s1, 2), "std_pc2": round(s2, 2),
                "count": len(c_data),
                "posisi_horizontal": "kanan" if m1 > 0 else "kiri",
                "posisi_vertikal": "atas" if m2 > 0 else "bawah",
                "kepadatan": "rapat" if (s1+s2)/2 < 1.0 else "tersebar"
            })
            
        distances = {}
        for i in centroids:
            for j in centroids:
                if i < j:
                    dist = np.sqrt((centroids[i][0]-centroids[j][0])**2 + (centroids[i][1]-centroids[j][1])**2)
                    distances[f"C{i}_C{j}"] = round(float(dist), 2)

        # Dendrogram Stats
        Z = linkage(X_scaled_arr, method='ward')
        threshold = 0.7 * Z[:, 2].max()
        merger_bawah = int(np.sum(Z[:, 2] < threshold))
        top3_heights = [round(float(h), 2) for h in sorted(Z[:, 2], reverse=True)[:3]]

        # Faktor Global Stats
        f_total = {pretty: int(df[raw].sum()) for raw, pretty in {"faktor_kelalaian": "Kelalaian", "faktor_pelanggaran": "Pelanggaran", "faktor_teknis": "Teknis"}.items()}
        total_k = sum(f_total.values())
        max_f = max(f_total, key=f_total.get)
        min_f = min(f_total, key=f_total.get)

        # Boxplot Stats
        boxplot_stats = {}
        for c_id in sorted(df['Cluster'].unique()):
            c_ages = df[df['Cluster'] == c_id]['Umur']
            q1, median, q3 = c_ages.quantile([0.25, 0.5, 0.75])
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            outliers = c_ages[(c_ages < lower_bound) | (c_ages > upper_bound)].tolist()
            boxplot_stats[f"Cluster {c_id}"] = {
                "Q1": round(float(q1), 1), "Median": round(float(median), 1), "Q3": round(float(q3), 1),
                "Min_Whisker": round(float(c_ages[c_ages >= lower_bound].min()), 1) if not c_ages[c_ages >= lower_bound].empty else 0,
                "Max_Whisker": round(float(c_ages[c_ages <= upper_bound].max()), 1) if not c_ages[c_ages <= upper_bound].empty else 0,
                "Outliers": [int(o) for o in outliers],
                "Homogenitas": "Homogen (IQR kecil)" if iqr <= 10 else "Heterogen (IQR besar)"
            }

        # Umur vs Faktor Stats
        def kategori_umur(u):
            if u <= 11: return "5-11 (Kanak-kanak)"
            elif u <= 16: return "12-16 (Remaja Awal)"
            elif u <= 25: return "17-25 (Remaja Akhir)"
            elif u <= 35: return "26-35 (Dewasa Awal)"
            elif u <= 45: return "36-45 (Dewasa Akhir)"
            elif u <= 55: return "46-55 (Lansia Awal)"
            elif u <= 65: return "56-65 (Lansia Akhir)"
            else: return "66-90 (Manula)"

        df['Kelompok Umur'] = df['Umur'].apply(kategori_umur)
        u_grouped = df.groupby('Kelompok Umur')[["faktor_kelalaian", "faktor_pelanggaran", "faktor_teknis"]].sum().reset_index()
        u_data = []
        for _, r in u_grouped.iterrows():
            total = r['faktor_kelalaian'] + r['faktor_pelanggaran'] + r['faktor_teknis']
            if total > 0:
                u_data.append({
                    "label": r['Kelompok Umur'], "total": int(total),
                    "kelalaian": int(r['faktor_kelalaian']), "pelanggaran": int(r['faktor_pelanggaran']), "teknis": int(r['faktor_teknis']),
                    "faktor_dominan": "Kelalaian" if r['faktor_kelalaian'] >= max(r['faktor_pelanggaran'], r['faktor_teknis']) else ("Pelanggaran" if r['faktor_pelanggaran'] >= r['faktor_teknis'] else "Teknis")
                })
        ranking = sorted([{"label": d['label'], "total": d['total']} for d in u_data], key=lambda x: x['total'], reverse=True)
        max_group_obj = ranking[0] if ranking else {"label": "N/A", "total": 0}
        
        payload = {
            "meta": {"total_data": len(df), "jumlah_cluster": len(summary_cluster), "silhouette_score": silhouette, "silhouette_kategori": sil_kat},
            "clusters": summary_cluster,
            "pca": {"explained_variance_ratio": evr, "cluster_positions": pca_positions, "jarak_antar_cluster": distances},
            "dendrogram": {
                "threshold": round(float(threshold), 2), "max_height": round(float(Z[:, 2].max()), 2), "jumlah_cluster": len(summary_cluster),
                "merger_di_bawah_threshold": merger_bawah, "total_merger": len(Z), "persen_merger_padat": round((merger_bawah/len(Z))*100, 1),
                "top3_merger_heights": top3_heights
            },
            "faktor_global": {
                "counts": f_total, "total": total_k, "faktor_dominan": max_f, 
                "persen_dominan": round((f_total[max_f]/total_k)*100, 1) if total_k > 0 else 0,
                "rasio_dominan_vs_terkecil": round(f_total[max_f]/f_total[min_f], 1) if f_total[min_f] > 0 else 0
            },
            "boxplot": boxplot_stats,
            "umur_faktor": {
                "data": u_data, "max_group": max_group_obj['label'], "max_total": max_group_obj['total'],
                "max_faktor": next((d['faktor_dominan'] for d in u_data if d['label'] == max_group_obj['label']), "N/A"),
                "ranking": ranking
            }
        }

        # 3. Prompt Gemini
        class NpEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, np.integer): return int(obj)
                if isinstance(obj, np.floating): return float(obj)
                if isinstance(obj, np.ndarray): return obj.tolist()
                return super(NpEncoder, self).default(obj)

        full_prompt = f"""
        Anda adalah sistem analisis kecelakaan lalu lintas berbasis data untuk Polres Madiun Kota. 
        Anda menerima data statistik hasil clustering AHC (Agglomerative Hierarchical Clustering) 
        dan bertugas memberikan interpretasi ilmiah untuk 5 diagram hasil analisis.

        ATURAN WAJIB:
        - Bahasa: Indonesia yang profesional namun mudah dipahami oleh petugas lapangan
        - Fokus: Interpretasi dan pembacaan data dari diagram — TIDAK ada rekomendasi kebijakan
        - Tone: Naratif, mengalir, bukan daftar label seperti "Kegunaan: ..., Point: ..."
        - Panjang: Setiap diagram cukup 1-2 paragraf ringkas (fokus pada data kunci)
        - Format output: JSON valid, semua value berupa HTML string

        DATA LENGKAP: {json.dumps(payload, cls=NpEncoder)}

        ===== INSTRUKSI PER DIAGRAM =====

        [1. PCA - Visualisasi Sebaran Klaster]
        Pola paragraf:
        - Para 1: Jelaskan sebaran cluster secara ringkas — apakah terpisah jelas, sebutkan jumlah cluster dan silhouette_score.
        - Para 2: Deskripsikan karakteristik posisi cluster dominan dan cluster terkecil secara singkat.
        - Tutup dengan tag: <p class="mt-4 font-bold text-blue-900 uppercase tracking-widest text-[10px]">Beberapa poin penting dalam diagram tersebut:</p><ul>2-3 poin singkat</ul>

        [2. Dendrogram - Struktur Hierarki]
        Pola paragraf:
        - Para 1: Jelaskan struktur hierarki secara ringkas, sebutkan nilai threshold dan jumlah cluster yang terbentuk.
        - Tutup dengan: <p class="mt-4 text-blue-900 font-bold uppercase tracking-widest text-[10px]">Hal penting yang perlu diperhatikan:</p><ul>2-3 poin singkat</ul>

        [3. Boxplot Umur per Klaster]
        Pola paragraf:
        - Cukup 1-2 paragraf ringkas yang membandingkan profil umur antar klaster berdasarkan median, tingkat homogenitas (lebar kotak), serta anomali (titik outlier jika ada). Jelaskan implikasinya apakah klaster tersebut berisi remaja, dewasa, atau bervariasi.

        [4. Faktor Penyebab Global]
        Pola paragraf:
        - Cukup 1 paragraf ringkas yang merangkum distribusi tiga faktor utama dan mengidentifikasi satu faktor yang paling berpengaruh.

        [5. Analisis Umur vs Faktor]
        Pola paragraf:
        - Para 1: Jelaskan tren umur vs faktor, sebutkan kelompok umur paling rentan (max_group) dan faktor utamanya.
        - Tutup dengan: <p class="mt-4 text-blue-900 font-bold uppercase tracking-widest text-[10px]">Kesimpulan Utama:</p><ul>2-3 poin ringkas</ul>


        ===== FORMAT RESPONS =====
        Respons HARUS berupa JSON valid murni tanpa markdown, tanpa teks di luar JSON:

        {{
          "pca": {{
            "paragraphs": "<p>...</p><p>...</p><p>...</p>",
            "poin_penting": "<ul class='list-disc ml-5 mt-2 space-y-1'><li>...</li><li>...</li><li>...</li></ul>"
          }},
          "dendrogram": {{
            "paragraphs": "<p>...</p><p>...</p><p>...</p>",
            "hal_penting": "<ul class='list-disc ml-5 mt-2 space-y-1'><li>...</li><li>...</li><li>...</li><li>...</li></ul>"
          }},
          "boxplot": {{
            "paragraphs": "<p>...</p><p>...</p>"
          }},
          "faktor_global": {{
            "paragraphs": "<p>...</p><p>...</p>",
            "penutup": "<p class='mt-2 italic text-blue-900'>...</p>"
          }},
          "umur_faktor": {{
            "paragraphs": "<p>...</p><p>...</p><p>...</p>",
            "kesimpulan": "<ul class='list-disc ml-5 mt-2 space-y-1'><li>...</li><li>...</li><li>...</li></ul>"
          }}
        }}
        """

        # Pakai API Key dari .env (Sesuai Permintaan User)
        try:
            parsed = parse_ai_json(request_ai_completion(full_prompt, 'ahc', timeout=60))
            
            request.session['ahc_ai_explain_cache'] = parsed
            request.session.modified = True
            request.session.save()
            
            return JsonResponse({"status": "ok", "data": parsed})
        except (KeyError, IndexError, json.JSONDecodeError) as je:
            print(f"[AI PARSE ERROR] {je}")
            return JsonResponse({
                "status": "error", 
                "message": f"Gagal memproses jawaban AI. Format tidak sesuai. Detail: {str(je)}",
                "raw_response": raw_text[:500] if 'raw_text' in locals() else "No text"
            }, status=500)

    except (ValueError, RuntimeError, requests.exceptions.Timeout) as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=504 if isinstance(e, requests.exceptions.Timeout) else 500)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[AI EXPLAIN ERROR] {error_trace}")
        return JsonResponse({"status": "error", "message": f"Analisis AI Gagal: {str(e)}"}, status=500)

# ================================
# REKOMENDASI AHC (AI)
# ================================
@login_required(login_url="login")
def ahc_rekomendasi(request):
    """
    Halaman Rekomendasi AHC.
    Menampilkan hasil rekomendasi yang sudah tersimpan di session.
    Jika method POST (AJAX), maka generate rekomendasi baru via AI.
    """
    # 1. Cek Data Clustering di Session
    summary_cluster = request.session.get("ahc_summary_cluster")
    if not summary_cluster:
        return render(request, "coreapp/ahc/rekomendasi.html", {"belum_clustering": True})

    # 2. Ambil data dari session (jika sudah ada)
    ai_rekomendasi = request.session.get("ahc_ai_rekomendasi")
    
    # Jika request AJAX POST -> Generate via AI
    if request.method == "POST" and request.headers.get("x-requested-with") == "XMLHttpRequest":
        try:
            # Siapkan Payload untuk AI
            silhouette = request.session.get("ahc_silhouette_score")
            jumlah_data = request.session.get("ahc_jumlah_data")
            ai_context = request.session.get("ahc_ai_context_data", {})
            
            payload = {
                "summary": summary_cluster,
                "ai_context": ai_context,
                "metadata": {
                    "total_kejadian": jumlah_data,
                    "silhouette": silhouette,
                    "lokasi": "Kota Madiun"
                }
            }

            prompt = f"""
            Anda adalah pakar Analisis Keselamatan Lalu Lintas Polresta Madiun. Berdasarkan hasil analisis clustering AHC (Agglomerative Hierarchical Clustering) dan profil demografi berikut:
            {json.dumps(payload)}

            Tugas Anda adalah merumuskan strategi penanganan kecelakaan yang KOMPREHENSIF, STRATEGIS, dan TAKTIS.
            
            CATATAN PENTING UNTUK ANALISIS:
            1. Faktor utama kecelakaan secara global adalah {ai_context.get('max_faktor')}.
            2. Kelompok umur paling rentan adalah {ai_context.get('max_umur_label')} dengan faktor dominan {ai_context.get('max_umur_faktor')}.
            3. Gabungkan temuan klaster (waktu/hari) dengan profil umur dan faktor ini untuk membuat rekomendasi yang koheren.

            ATURAN WAJIB:
            1. Output harus JSON VALID murni tanpa markdown, tanpa teks tambahan.
            2. Bahasa Indonesia profesional dan formal.
            3. Bagian "ringkasan" HARUS menyebutkan korelasi antara kelompok umur paling rentan ({ai_context.get('max_umur_label')}) dengan faktor penyebabnya.
            4. Matriks Intervensi harus memberikan solusi spesifik untuk menangani faktor {ai_context.get('max_faktor')} pada kelompok usia tersebut.

            FORMAT JSON:
            {{
                "ringkasan": "Sintesis hasil analisis: gabungkan data faktor dominan global, karakteristik klaster, dan profil kelompok umur paling rentan.",
                "prioritas_tinggi": [
                    {{
                        "waktu": "Cluster X - (Faktor Dominan + Kelompok Umur Relevan)",
                        "kejadian": "Jumlah Kejadian",
                        "tindakan": {{
                            "patroli": "Tindakan pencegahan spesifik (misal: edukasi untuk kelompok umur Y di waktu Z)",
                            "infrastruktur": ["Rekomendasi 1", "Rekomendasi 2"]
                        }}
                    }}
                ],
                "jadwal_patroli": [
                    {{ "hari": "Nama Hari", "jam": "Range Jam", "fokus": "Aspek yang diawasi", "unit": "X" }}
                ],
                "target_kpi": {{
                    "pengurangan": "Estimasi %",
                    "indikator": ["Indikator 1", "Indikator 2"]
                }},
                "program": {{
                    "jangka_pendek": ["Program 1", "Program 2"],
                    "jangka_menengah": ["Program 3", "Program 4"]
                }},
                "catatan": "Pesan penutup strategis."
            }}
            """

            parsed = parse_ai_json(request_ai_completion(prompt, 'ahc', timeout=45))
            request.session["ahc_ai_rekomendasi"] = parsed
            request.session.modified = True
            
            return JsonResponse({"status": "ok", "data": parsed})

        except Exception as e:
            print(f"[AHC REKOMENDASI ERROR] {e}")
            return JsonResponse({"status": "error", "message": str(e)}, status=500)

    # 3. Render Halaman (Regular GET)
    context = {
        "ai_data": ai_rekomendasi,
        "belum_ai": ai_rekomendasi is None,
        "today": timezone.now().strftime("%d %B %Y")
    }
    return render(request, "coreapp/ahc/rekomendasi.html", context)

