# Android maç videosu

## Değişen / eklenen dosyalar

| Dosya | İşlev |
| --- | --- |
| `buildozer.spec` | API 36, foreground izinleri, Java/AAR ekleme |
| `main.py` | Arka plana geçişte kaydı sonlandırma |
| `services/match_settings.py` | Varsayılan kapalı `record_video` ayarı |
| `screens/setup_screen.py` | Kalıcı kayıt anahtarı ve sessiz video açıklaması |
| `screens/router.py` | İzin/hazırlık sonrası maçı açma, tek oturum, bildirimler |
| `screens/match_screen.py` | İlk kare başlangıç kapısı, sonuç flip olayı ve temizleme |
| `services/video_recording.py` | Python koordinatörü, Android Activity-result adaptörü |
| `android_src/org/simomatch/capture/CaptureService.java` | Foreground service, donanım codec, muxer ve MediaStore |
| `android_src/capture_manifest.xml` | Servis manifest kaynağı |
| `android_src/capture_manifest.aar` | Gradle tarafından birleştirilen küçük manifest paketi |
| `tools/build_capture_manifest.py` | AAR'ı yeniden üreten bağımlılıksız araç |
| `tests/test_video_recording.py` | Yeni koordinasyon ve entegrasyon testleri |
| `docs/ANDROID_VIDEO.md` | Bu rapor ve cihaz test listesi |

Son doğrulama: Windows Python 3.10.9 / Kivy 2.3.1 ile **474 test geçti**
(106,18 saniye). Java 8 sözdizimi ayrıştırması başarılı. Android SDK ile Java
derlemesi, APK üretimi ve gerçek MediaProjection/encoder/MediaStore çalıştırması
bu ortamda yapılmadı. Fizik motoru, ses motoru, takım kayıt sistemi ve arena efekt
dosyalarında değişiklik yoktur. Test verileri proje içindeki geçici dizinlerde tutuldu.

## Uygulanan akış

Maç Oluştur ekranındaki **MAÇ VİDEOSUNU KAYDET** tercihi varsayılan kapalıdır.
Tercih, uygulamanın kalıcı veri dizinindeki `video_preferences.json` dosyasına
atomik olarak yazılır. Takım ve arka plan kayıtları değiştirilmez.
Windows bu tercihi hatırlar ancak Android API çağırmaz; kullanıcıya kayıt
desteklenmediğini bildirerek maçı normal başlatır.

Android 10+ üzerinde her yeni maç/yeniden başlatma için yeni ekran kayıt izni
istenir. İzin ekranı Kivy'yi geçici olarak duraklatabildiği için bu aşamadaki
`on_pause` izin isteğini iptal etmez. Kullanıcı reddederse maç kayıtsız açılır.

İzin sonrası Java `CaptureService`, `mediaProjection` türünde foreground service
olarak başlar. HandlerThread üzerinde donanım H.264 encoder ve MediaMuxer
hazırlanır. Tek kullanımlık MediaProjection için callback kaydedilir ve **bir**
VirtualDisplay oluşturulur; geri sayım sırasında Surface bağlı değildir.

Encoder hazırlanınca mevcut 3-2-1 geri sayımı başlar. Sayaç kaldırıldıktan sonra
Surface bağlanır. İlk kodlanmış kare MP4'e yazılmadan simülasyon ilerletilmez.
Ardından mevcut motorun başlangıç olayı/düdüğü çalışır. Encoder gecikmesi fizik
motoruna birikmiş zaman olarak aktarılmaz. İlk kare ile düdük arasındaki gecikme
Python durum sorgulama aralığı (30 ms), ekran yenilemesi ve cihaz yüküne bağlıdır;
ses/video örnek düzeyinde eşzamanlılık iddiası yoktur.

Mevcut gol/kart bildirimleri bittikten sonra sonuç paneli görünür. İlk `Window`
flip olayından itibaren **3 saniye** sonra EOS gönderilir. Sabit sonuç görüntüsü
için encoder'a önceki kareyi tekrar etme ayarı verilir. UI/encoder zamanlayıcıları
ve kare aralığı nedeniyle video süresinde birkaç karelik sapma olabilir. Sonuç
ekranı kapanmaz; yalnızca kayıt durur.

## Video ve ses

- MP4 / donanım AVC (H.264), azami 30 FPS, hedef 6 Mbps.
- Dikey oran korunur; azami 1080 genişlik ve 1920 yükseklik. Örneğin uzun ekranlı
  bir telefonda yükseklik sınırı nedeniyle genişlik 1080'den küçük olabilir.
- Encoder hizalama gereksinimleri nedeniyle boyutlar birkaç piksel yuvarlanabilir.
- Uygun donanım encoder yoksa yazılım encoder'a yük bindirmek yerine kayıt
  kapatılır, kullanıcı bilgilendirilir ve normal maç başlar.
- Ekran oranı kayıt sırasında değişirse mevcut bölüm sonlandırılır; aynı
  MediaProjection ile ikinci VirtualDisplay oluşturulmaz.
- **Bu sürüm yalnızca sessiz video kaydeder.** Mikrofon açılmaz. `RECORD_AUDIO`
  izni istenmez. Başlangıç/bitiş düdükleri, gol sesleri ve takım müzikleri videoda
  bulunmaz. Seçim alanı ve başarı bildirimi bunu açıkça belirtir.
- AudioPlaybackCapture değerlendirildi; SDL2 efektleri ile bağımsız MediaPlayer
  müziklerini kapsamak için ayrıca capture politikası, AudioRecord, AAC encoder
  ve ortak zaman tabanlı muxing gerekir. Bu hat bu sürümde uygulanmadı.

## Saklama ve iptal

Dosya, `MediaStore.Video` üzerinden `Movies/Simomatch/` altında oluşturulur.
İsme tarih/saat ve benzersiz ek eklenir. Dosya `IS_PENDING=1` durumunda tutulur.
EOS/muxer kapanışı ve metadata/küçük kare çözümleme doğrulaması sonrası pending
kaldırılır. Ancak bundan sonra `Video kaydedildi (sessiz).` bildirimi gösterilir.
Geniş depolama izni kullanılmaz.

Maçtan çıkış, uygulamanın arka plana gitmesi, sistemin projection'ı kapatması,
kilit ekranı ve encoder hataları aynı idempotent temizleme yolunu kullanır.
Geçerli kısmi MP4 varsa saklanır; kapanışı/doğrulaması başarısız dosya yayımlanmaz.
Süreç zorla öldürülürse sonlandırma garanti edilemez. Servis, bir sonraki açılışında
yalnızca kendisinin önceki pending URI kaydını temizler; tamamlanmış videolara
ve kullanıcı dosyalarına dokunmaz. Yeni bir oturum öncekinin bitmesini bekler.

## Derleme

`buildozer.spec` API 36 / arm64-v8a kullanır. Java kodu `android.add_src` ile,
servis bildirimi `android.add_aars` üzerinden küçük bir manifest-only AAR ile
Gradle manifest merger'a eklenir. Oluşturulmuş AndroidManifest.xml elle değiştirilmez.
Named AAR bağımlılığının çözülmesi için `android.add_gradle_repositories = flatDir { dirs 'libs' }`
gereklidir; p4a develop AAR'ı Gradle proje kökündeki `libs/` dizinine kopyalar.
`extra_manifest_application_arguments` kullanılmaz: bazı p4a sürümlerinde yalnızca
application özniteliklerini kabul eder, servis child etiketi ekleyemez.
Kaynak `android_src/capture_manifest.xml`, tekrarlanabilir paket
`android_src/capture_manifest.aar` içindedir. Kaynak değişirse
`python tools/build_capture_manifest.py` çalıştırın; APK derlemek için bu arşiv
projede hazırdır. AAR çalıştırılabilir kod/kütüphane içermez.

İzinler: `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MEDIA_PROJECTION`.
Service exported değildir ve `foregroundServiceType="mediaProjection"` kullanır.
Servis `START_NOT_STICKY` döner: tüketilmiş izinle kendiliğinden yeniden başlamaz.

Bu Windows çalışma ortamında Buildozer, python-for-android ve Android SDK
bulunmadığından Android Java derlemesi/APK üretimi yapılmadı; kullanılan p4a
sürümü de yerelden tespit edilemedi. PyCharm'ın beraberindeki JDK ile yalnızca
Java sözdizimi ayrıştırması yapılabilir; bu Android API derlemesi değildir.
Linux/WSL derleme ortamınızda API 36 destekleyen p4a
ve Java/AAR ekleme seçenekleri gereklidir. Yeni manifest/Java için APK'yi
yeniden derleyin (`buildozer android debug`); eski APK'de özellik bulunmaz.

## Cihaz test listesi

1. Kayıt kapalı maç: eski geri sayım, fizik, goller, kartlar ve efektleri kontrol edin.
2. Kayıt açık: izin reddi normal maçı açmalı; onay hazırlık sonrası geri sayımı açmalı.
3. Videoda izin ekranı/3-2-1 bulunmamalı; ilk hareketler ve son skor bulunmalı.
4. Maç süresine ek yaklaşık 3 saniyelik görünür sonuç ekranını kontrol edin.
5. Galeri/Google Photos'ta dosyayı açın; portre, oran, çözünürlük ve sessizliği kontrol edin.
6. Sonuç ekranı kapanmadan tekrar başlatın; yeni izin istenmeli, eski oturum kullanılmamalı.
7. Maçtan çıkış, ana ekrana gitme, kilitleme ve Android kayıt durdurma kontrolünü deneyin.
8. Boş depolama azlığı ve encoder hatasında başarı mesajı/bozuk Galeri öğesi olmamalı.
9. Fire/Electric/Rainbow temalarında ısınma ve FPS kontrolü yapın; fizik hızını karşılaştırın.
10. Uzun ekranlı/çentikli cihazda kayıt ile ekrandaki arka plan/HUD oranını karşılaştırın.

Otomatik Python testleri donanım encoder'ını ve MediaStore'u çalıştırmaz.
API akışı ve Windows izolasyonu test edilse de Galeri'de açılma, gerçek MP4
zamanlaması, termal/FPS etkisi ve OEM davranışları cihaz üzerinde doğrulanmalıdır.

## Kaynaklar

- https://developer.android.com/media/grow/media-projection
- https://developer.android.com/media/platform/av-capture
- https://developer.android.com/reference/android/media/MediaFormat
- https://github.com/kivy/buildozer/blob/master/buildozer/default.spec
