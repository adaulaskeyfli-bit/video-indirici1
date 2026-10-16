# Video İndirici — iPhone web uygulaması

Python (Flask + yt-dlp) bir sunucuda çalışır. iPhone'da Safari'den açılır ve **Ana Ekrana Ekle** ile uygulama gibi kurulur.
İndirilen videolar uygulamanın **İÇİNDE** saklanır ve internet olmadan da **İndirilenler** sekmesinden izlenebilir.

## Kullanım
1. Uygulamayı aç, **İndir** sekmesinde linki yapıştır, kaliteyi seç, **İndir**'e bas.
2. Video önce sunucuya, sonra telefona aktarılır ve uygulama içine kaydedilir.
3. **İndirilenler** sekmesinde videoya dokununca oynar. Buradan **Sil** ile kaldırabilir, **Paylaş** ile istersen Fotoğraflar'a / Dosyalar'a da kopyalayabilirsin.

## İnternete koyma (Render.com, ücretsiz)
1. Bu klasörü bir GitHub deposuna yükle.
2. render.com → New → Web Service → depoyu seç. Runtime: **Docker** (ffmpeg'i de kurar).
3. Environment kısmına `APP_SIFRE` ekle (başkaları kullanamasın).
4. Verilen `https://...onrender.com` adresini iPhone'da **Safari**'de aç → Paylaş → **Ana Ekrana Ekle**.
   Videolar sadece ana ekrandaki simgeden açılan uygulamada saklanır. Safari sekmesiyle ana ekran uygulamasının depoları ayrıdır.

## Evdeki bilgisayarda çalıştırma (YouTube sunucuyu engellerse)
```
pip install -r requirements.txt
python app.py
```
iPhone aynı Wi-Fi'dayken Safari'de `http://<bilgisayarın-IP'si>:5000` adresini aç.
Not: Ana ekrana ekleme ve çevrimdışı açılma, adres `https://` olduğunda en iyi çalışır (Render bunu otomatik sağlar).

## Bilinmesi gerekenler
- YouTube bulut sunucularını sık sık "bot kontrolü" ile engeller. Uygulama bunu açıkça bildirir.
- Ücretsiz Render sunucusu boşta uyur, ilk açılış yaklaşık 1 dakika sürebilir.
- Videolar telefonun belleğinde tutulur. Çok büyük dosyalar (1 GB üstü) aktarım sırasında sorun çıkarabilir; 720p önerilir.
- iOS, ana ekrana eklenmiş uygulamaların verilerini genelde korur. Yine de önemli videoları **Paylaş** ile Fotoğraflar'a da kaydetmek iyi olur.
- Sunucudaki kopyalar telefona aktarıldıktan hemen sonra, aktarılmazsa 30 dakika içinde silinir. 1 saatten uzun videolar reddedilir.
