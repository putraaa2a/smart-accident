from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('coreapp', '0012_alter_user_email'),
    ]

    operations = [
        migrations.CreateModel(
            name='AhcPreprosesing',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('no_referensi', models.CharField(blank=True, max_length=50, null=True)),
                ('umur', models.IntegerField(default=0)),
                ('tkp', models.CharField(blank=True, max_length=255)),
                ('penyebab', models.CharField(blank=True, max_length=255)),
                ('hari', models.CharField(blank=True, max_length=20)),
                ('tanggal', models.DateField(blank=True, null=True)),
                ('jam', models.CharField(blank=True, max_length=10)),
                ('jenis_kendaraan', models.CharField(blank=True, max_length=100)),
                ('tipe_kendaraan', models.CharField(blank=True, max_length=100)),
                ('kerugian_material', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name_plural': 'AHC Preprocessing',
                'db_table': 'ahc_preprosesing',
                'ordering': ['-tanggal', '-jam'],
            },
        ),
        migrations.CreateModel(
            name='KmeansPreprosesing',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('no_referensi', models.CharField(blank=True, max_length=50, null=True)),
                ('umur', models.IntegerField(default=0)),
                ('tkp', models.CharField(blank=True, max_length=255)),
                ('penyebab', models.CharField(blank=True, max_length=255)),
                ('hari', models.CharField(blank=True, max_length=20)),
                ('tanggal', models.DateField(blank=True, null=True)),
                ('jam', models.CharField(blank=True, max_length=10)),
                ('jenis_kendaraan', models.CharField(blank=True, max_length=100)),
                ('tipe_kendaraan', models.CharField(blank=True, max_length=100)),
                ('kerugian_material', models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name_plural': 'K-Means Preprocessing',
                'db_table': 'kmeans_preprosesing',
                'ordering': ['-tanggal', '-jam'],
            },
        ),
    ]
