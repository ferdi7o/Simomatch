# MP4 oyun sesi — entegrasyon ve cihaz doğrulaması

## Kapsam ve doğrulama sınırı

Önceki CaptureService yalnızca video/avc track'i ekliyordu. Efektler Kivy SoundLoader/SDL2, Android takım müzikleri MediaPlayer üzerinden oynatılıyor. Yeni yol bunları oynatım çıkışından yakalamayı dener; ses motorunu yeniden kurmaz. SDL2'nin telefondaki gerçek ses yolu/capture politikası yalnızca cihaz testiyle doğrulanabilir. Bu ortamda Android SDK, Java derleyicisi, ADB ve telefon yoktur; Java/APK derlemesi ve gerçek ses yakalama doğrulanmış değildir.

Windows doğrulaması: tam pytest paketi 573 geçti (95,04 s). Sesin hazır olmasını bekleyen son Java başlangıç düzenlemesinden sonra ilgili 63 host testi tekrar geçti (5,76 s). Bu testler Android AAC codec'ini çalıştırmaz; izin/oturum koordinasyonu, geriye uyum, kaynak/manifest sözleşmeleri ve PCM denetim aracını kapsar. Kaynak/Buildozer kontrol aracı başarılı; APK DEX kontrolü için yeni APK gerekir.

## Mekanizma

- MediaProjection onayından sonra hazırlanan PlaybackAudio, AudioPlaybackCaptureConfiguration kullanır. Yalnızca Process.myUid() ve GAME / MEDIA / UNKNOWN kullanım türleri eşleşir. Başka uygulamaların sesi veya mikrofon kaynağı seçilmez.
- Android RECORD_AUDIO izni gerektirir. Sistem izin penceresi mikrofon adını kullanabilir; uygulama önce yalnızca oyun sesinin kaydedileceğini açıklar. Ret veya SESSİZ KAYDET normal ekran kayıt onayına devam eder. Mikrofon foreground service türü eklenmedi.
- Manifest allowAudioPlaybackCapture=true; AudioManager uygulama politikası ve MediaPlayer oynatıcı politikası ALLOW_CAPTURE_BY_ALL. SDL2 sağlayıcısının daha kısıtlayıcı bir politikası varsa bunlar tek başına yeterli değildir.
- PCM 48 kHz / 16 bit / mono, AAC-LC 128 kbps. AAC ayrı iş parçacığı ve geçici M4A'ya yazılır. Video encoder, yüzey ve ilk kare onay akışı korunmuştur; ses begin() sırasında başlar, ilk video karesinden sonra mevcut düdük/fizik akışı devam eder.
- PCM konumu ve AudioTimestamp MONOTONIC ile ses başlangıcı hesaplanır. Video encoder'ın ilk ham PTS'iyle farkı remux sırasında uygulanır. Video öncesindeki AAC paketleri atılır; son video zamanını aşan paketler eklenmez. Saat farkı 2 saniyeden büyükse senkronizasyon uydurulmaz; sessiz video korunur. Ses kartının/SDL çıkışının gecikmesi ayrıca telefonda ölçülmelidir.
- Sonuç ekranının mevcut 3 saniyelik kaydı değiştirilmedi. Sonlandırma sırasında AAC EOS beklenir, track'ler yeniden kodlanmadan ayrı geçici MP4'e birleştirilir. Kivy/UI thread üzerinde kodlama veya dosya kopyalama yapılmaz.
- Gerçek çıktı MP4'ün AAC track'i decoder ile PCM'e çevrilir; örnek sayısı, |sample|>8 sayısı, peak ve RMS ölçülür. Hiç ses yoksa veya RMS <= 1 ise sesli başarı bildirilmez. Bu kontrol bütün ses türlerinin ayrı ayrı yakalandığını kanıtlamaz.
- AAC/remux/izin/depolama/doğrulama hatasında bilinen iyi sessiz MP4 korunur. Sesli aday ayrı pending MediaStore satırına kopyalanır; aday yayımlanana kadar özgün video silinmez. Yarıda kalan iki pending satır sonraki oturumda temizlenir. MediaStore Movies/Simomatch ve tek oturum kuralı korunur.

## Maliyet

Canlı AAC okuma/kodlama video ve Kivy thread'lerinden ayrıdır. Remux, dosya kopyalama ve AAC decode doğrulaması maçtan sonra ek süre alır; sonuç ekranı açık kalır. Geçici AAC/MP4 ve ayrı pending aday nedeniyle ek boş depolama gerekir. Yer yetmezse sessiz video korunur. RAM'de tam maç tutulmaz. Gerçek cihaz CPU, sıcaklık ve FPS ölçümü henüz yapılmadı.

## WSL derlemesi

Kodları ve android_src dosyalarını aktar. buildozer.spec rsync dışında tutuluyorsa WSL'de RECORD_AUDIO eklenmesi gereklidir. Python bağımlılıkları, p4a develop ve SDK/NDK ayarları değiştirilmez.

```bash
python3 tools/build_capture_manifest.py
python3 tools/check_android_capture.py --apply --spec buildozer.spec
buildozer -v android debug
python3 tools/check_android_capture.py --apk bin/YENI_APK_ADI.apk
```

Son komut CaptureService DEX tanımını kontrol eder; cihaz çalışmasını kanıtlamaz. PlaybackAudio ve AudioMovie de android.add_src altındaki aynı package içindedir. SDK apkanalyzer ile yeni APK'deki yardımcıları ayrıca denetleyebilirsin:

```bash
apkanalyzer dex packages --defined-only bin/YENI_APK_ADI.apk | grep -E 'CaptureService|PlaybackAudio|AudioMovie'
```

Manifest-only AAR yeniden üretildi: uygulama capture politikası ve RECORD_AUDIO içerir. Servis türü yalnızca mediaProjection; mevcut izinler ve Java kaynak yolu korunur. Üretilmiş .buildozer dosyalarına elle yama yapılmadı.

## Telefon testleri

1. Önce kayıt kapalı normal maç: efektler, takım müzikleri, düdükler ve sonuç ekranı değişmemeli.
2. Kayıt açık, ses iznini reddet: maç ve MP4 çalışmalı, bildirim açıkça sessiz demeli.
3. Ses izni ve her maçın taze MediaProjection onayını ver. Telefonun medya sesini duyulabilir düzeye getir. Maç oynat; çarpışma, gol ve özel takım müziği olsun. Sonuç ekranında kaydın bitmesini bekle.
4. Galeri'de videoyu sesli aç. Başlangıç düdüğü/hareket başlangıcı, gol/özel müzik ve bitiş düdüğü/sonuç ekranını ayrı ayrı karşılaştır. Yalnız müzik duyulup düdük/çarpışma duyulmuyorsa SDL2 capture yolu hâlâ doğrulanmamıştır; sesli track tek başına yeterli değildir.
5. Kayıt bitince logcat'te AUDIO_PCM_SUMMARY, AUDIO_VIDEO_OFFSET_US ve AUDIO_MP4_VERIFIED ara. nonzero ve rms sıfır olmamalı. AUDIO_*_FALLBACK_SILENT varsa hata ayrıntısını paylaş.
6. Videoyu bilgisayara çek; aşağıdaki aracı ffmpeg/ffprobe PATH'teyken çalıştır. Her iki track ve decode edilmiş ses aranır; başarısız durumda çıkış kodu 1 olur. Rapor ilk duyulabilir örnek, RMS, peak, track başlangıç/sürelerini gösterir. Bu otomatik rapor olay bazında AV senkronizasyonunu tek başına kanıtlamaz.

```bash
python3 tools/check_recorded_audio.py kaydedilen_mac.mp4
```

7. Üç ardışık maç, hızlı yeniden başlatma, uygulamadan çıkma/arka plana alma, ekran kilidi, projection iptali, ses iznini ayarlardan kaldırma ve düşük depolama testlerini yap. Sessiz video fallback'i bozulmamalı; bozuk aday Galeri'ye başarılı kayıt gibi eklenmemeli.

Resmî referanslar:
- https://developer.android.com/media/platform/av-capture
- https://developer.android.com/reference/android/media/AudioPlaybackCaptureConfiguration
- https://developer.android.com/reference/android/media/AudioRecord
