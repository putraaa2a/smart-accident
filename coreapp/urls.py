from django.urls import path
from . import views

urlpatterns = [
    # Homepage
    path('', views.homepage_view, name='homepage'),

    path('tentang/', views.tentang_view, name='tentang'),
    path('keselamatan/', views.keselamatan_view, name='informasikeselamatan'),
    path('fitur/', views.fitur_view, name='fitur'),
    path('faq/', views.faq_view, name='faq'),
    path('guide/', views.guide_view, name='guide'),
    
    # Authentication
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # ── Superadmin: Kelola Akun Admin ──
    path('superadmin/admins/', views.admin_list, name='admin_list'),
    path('superadmin/admins/create/', views.admin_create, name='admin_create'),
    path('superadmin/admins/<int:user_id>/edit/', views.admin_update, name='admin_update'),
    path('superadmin/admins/<int:user_id>/delete/', views.admin_delete, name='admin_delete'),
    path('superadmin/admins/<int:user_id>/toggle/', views.admin_toggle_active, name='admin_toggle_active'),

    path('superadmin/polres/', views.polres_list, name='polres_list'),
    path('superadmin/polres/create/', views.polres_create, name='polres_create'),
    path('superadmin/polres/<int:pk>/edit/', views.polres_update, name='polres_update'),
    path('superadmin/polres/<int:pk>/delete/', views.polres_delete, name='polres_delete'),

    path('superadmin/polda/', views.polda_list, name='polda_list'),
    path('superadmin/polda/create/', views.polda_create, name='polda_create'),
    path('superadmin/polda/<int:pk>/edit/', views.polda_update, name='polda_update'),
    path('superadmin/polda/<int:pk>/delete/', views.polda_delete, name='polda_delete'),
    # Dashboard (Admin)
    path('dashboard/', views.dashboard_view, name='dashboard'),

    # Profil Pengguna
    path('profile/', views.profile, name='profile'),
    
    
    # Ruas Jalan (Admin)
    path('ruas-jalan/', views.ruas_jalan_list, name='ruas_jalan_list'),
    path('ruas-jalan/create/', views.ruas_jalan_create, name='ruas_jalan_create'),
    path('ruas-jalan/<int:pk>/', views.ruas_jalan_detail, name='ruas_jalan_detail'),
    path('ruas-jalan/<int:pk>/update/', views.ruas_jalan_update, name='ruas_jalan_update'),
    path('ruas-jalan/<int:pk>/delete/', views.ruas_jalan_delete, name='ruas_jalan_delete'),
    path('ruas-jalan/<int:pk>/generate-segmen/', views.generate_segmen, name='generate_segmen'),
    
    # Kecelakaan
    path('kecelakaan/', views.kecelakaan_list, name='kecelakaan_list'),
    path('kecelakaan/create/', views.kecelakaan_create, name='kecelakaan_create'),
    path('kecelakaan/<int:pk>/', views.kecelakaan_detail, name='kecelakaan_detail'),
    path('kecelakaan/<int:pk>/update/', views.kecelakaan_update, name='kecelakaan_update'),
    path('kecelakaan/<int:pk>/delete/', views.kecelakaan_delete, name='kecelakaan_delete'),
    path('kecelakaan/segmen/<int:segmen_id>/', views.segmen_kecelakaan_detail, name='segmen_kecelakaan_detail'),
    
    # Upload Kecelakaan Raw
    path('kecelakaan-raw/upload/', views.upload_kecelakaan_raw, name='upload_kecelakaan_raw'),
    path('kecelakaan-raw/', views.kecelakaan_raw_list, name='kecelakaan_raw_list'),
    path('kecelakaan-raw/<int:pk>/', views.kecelakaan_raw_detail, name='kecelakaan_raw_detail'),
    path('kecelakaan-raw/<int:pk>/delete/', views.kecelakaan_raw_delete, name='kecelakaan_raw_delete'),
    
    # Upload Kecelakaan Preprosesing
    path('kecelakaan-preprosesing/upload/', views.upload_kecelakaan_preprosesing, name='upload_kecelakaan_preprosesing'),
    path('kecelakaan-preprosesing/download-template/', views.download_template_preprosesing, name='download_template_preprosesing'),
    path('k-means/download-template/', views.download_template_clustering, name='download_template_clustering'),
    path('kecelakaan-preprosesing/', views.kecelakaan_preprosesing_list, name='kecelakaan_preprosesing_list'),
    path('kecelakaan-preprosesing/<int:pk>/', views.kecelakaan_preprosesing_detail, name='kecelakaan_preprosesing_detail'),
    path('kecelakaan-preprosesing/<int:pk>/delete/', views.kecelakaan_preprosesing_delete, name='kecelakaan_preprosesing_delete'),
    
    # Analisis
    path('analisis/', views.analisis_view, name='analisis'),
    
    # Map 
    path('peta/', views.map_view, name='map'),
    path('peta-user/', views.peta_user_view, name='peta_user'),

    # ================= KMEANS =================
    # ================= CLUSTER DATA (Unified) =================
    path('laka-mentah/', views.laka_mentah_list, name='laka_mentah_list'),
    path('laka-mentah/tambah/', views.laka_mentah_tambah, name='laka_mentah_tambah'),
    path('laka-mentah/edit/<int:pk>/', views.laka_mentah_edit, name='laka_mentah_edit'),
    path('laka-mentah/import/', views.laka_mentah_import, name='laka_mentah_import'),
    path('laka-mentah/hapus/<int:pk>/', views.laka_mentah_hapus, name='laka_mentah_hapus'),
    path('laka-mentah/hapus-duplikat/', views.laka_mentah_hapus_duplikat, name='laka_mentah_hapus_duplikat'),
    path('laka-mentah/hapus-semua/', views.laka_mentah_hapus_semua, name='laka_mentah_hapus_semua'),

    path('cluster-data/', views.cluster_data_list, name='cluster_data_list'),
    path('cluster-data/tambah/', views.cluster_data_tambah, name='cluster_data_tambah'),
    path('cluster-data/edit/<int:pk>/', views.cluster_data_edit, name='cluster_data_edit'),
    path('cluster-data/import/', views.cluster_data_import, name='cluster_data_import'),
    path('cluster-data/hapus/<int:pk>/', views.cluster_data_hapus, name='cluster_data_hapus'),
    path('cluster-data/hapus-duplikat/', views.cluster_data_hapus_duplikat, name='cluster_data_hapus_duplikat'),
    path('cluster-data/hapus-semua/', views.cluster_data_hapus_semua, name='cluster_data_hapus_semua'),
    path('k-means/proses/', views.proses_cluster, name='proses_cluster'),
    path('k-means/preprocessing/', views.preprocessing, name='preprocessing'),
    path('k-means/hasil/', views.hasil, name='hasil'),
    path('k-means/rekomendasi/', views.rekomendasi_kebijakan, name='rekomendasi_kebijakan'),
    path('k-means/ai-recommendation/', views.get_ai_recommendation, name='get_ai_recommendation'),
    path('k-means/analyze-dashboard/', views.analyze_accident_clustering, name='analyze_dashboard'),
    path('k-means/save-ai-config/', views.save_ai_config, name='save_ai_config'),
    path('k-means/reset/', views.reset_k_means, name='reset_k_means'),

    # path('tambah-data/', views.tambah_data, name='tambah_data'),
    path('ajax/load-kecamatan/', views.load_kecamatan, name='ajax_load_kecamatan'),
    path('ajax/load-kelurahan/', views.load_kelurahan, name='ajax_load_kelurahan'),
   

    # ================= AHC =================   

    # AHC URLS
    path('ahc/data/', views.ahc_data, name='ahc_data'),
    path('ahc/proses/', views.ahc_proses, name='ahc_proses'),
    path('ahc/preprocessing/', views.preprocessing_data, name='preprocessing_data'),
    path('ahc/hasil/', views.ahc_hasil, name='ahc_hasil'),
    path('proses-ahc/', views.proses_ahc, name='proses_ahc'),
    path('ahc/reset/', views.reset_ahc, name='reset_ahc'),
    path('ahc/ai-explain/', views.ahc_ai_explain, name='ahc_ai_explain'),
    path('ahc/rekomendasi/', views.ahc_rekomendasi, name='ahc_rekomendasi'),


    # API
    path('api-data/kecelakaan/', views.api_data_page, {'api_name': 'kecelakaan'}, name='api_kecelakaan_preprosesing_page'),
    path('api-data/ahc/', views.api_data_page, {'api_name': 'ahc'}, name='api_ahc_preprosesing_page'),
    path('api-data/kmeans/', views.api_data_page, {'api_name': 'kmeans'}, name='api_kmeans_preprosesing_page'),
    path('api/kecelakaan-preprosesing/', views.api_kecelakaan_preprosesing, name='api_kecelakaan_preprosesing'),
    path('api/segmen/geojson/', views.api_segmen_geojson, name='api_segmen_geojson'),
    path('api/ahc-preprosesing/', views.api_ahc_preprosesing, name='api_ahc_preprosesing'),
    path('api/kmeans-preprosesing/', views.api_kmeans_preprosesing, name='api_kmeans_preprosesing'),
    path('api/segmen/thresholds/', views.api_threshold_data, name='api_threshold_data'),
    path('api/segmen/check-update/', views.api_data_update_check, name='api_data_update_check'),
    path('api/kecelakaan/geojson/', views.api_kecelakaan_geojson, name='api_kecelakaan_geojson'),
    path('api/analisis/statistik/', views.api_analisis_statistik, name='api_analisis_statistik'),
    
    # Geoapify API
    path('api/geoapify/routing/', views.api_geoapify_routing, name='api_geoapify_routing'),
    path('api/geoapify/reverse-geocoding/', views.api_geoapify_reverse_geocoding, name='api_geoapify_reverse_geocoding'),

]


