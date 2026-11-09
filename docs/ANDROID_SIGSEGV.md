# Adreno 750 / Android 16 maç başlangıcı incelemesi

## Kesin olarak bilinenler

Verilen backtrace, SIGSEGV'nin SDLThread üzerinde Adreno GLES sürücüsü ve Kivy
VBO/instruction/compiler çağrı zincirinde oluştuğunu gösteriyor. Bu tek başına
hangi Mesh/Texture'ın veya driver/context durumunun hatayı tetiklediğini göstermez.
Android cihazda yeniden üretim, son aşama logları ve daha ayrıntılı tombstone
olmadan **kesin SIGSEGV kök nedeni tespit edildi denemez**.

Kayıt kapalı yol: `start_match -> _open_match -> MatchScreen`.
`VideoRecording.prepare`, `AndroidCapture`, izin ve Java foreground service bu
yolda çağrılmaz. Koordinatör nesnesinin varlığı kayıt oturumu başlatmaz.

Kayıt açık yol: `prepare -> izin sonucu -> Java encoder hazırlığı -> Clock
üzerinde prepared callback -> _open_match -> MatchScreen`. Java sonucu Kivy'ye
Clock üzerinden döner. Servis yalnızca kendi MediaCodec input Surface'ini
VirtualDisplay'e bağlar; Kivy/SDL Surface veya EGL context'ini değiştiren doğrudan
çağrısı yoktur. Bu, GPU sürücüsündeki dolaylı bir etkileşimi elemez.

Mevcut Android immersive servisi Android UI thread'inde window ayarları yapar;
Kivy güvenlik paylarını Clock üzerinden aktarır. Bu incelemede değiştirilmedi.

## Tespit edilen uygulama sorunları ve dar düzeltmeler

1. Arena katmanı Mesh'i ilk oluşturulduğunda sıfır vertex ile 576 index taşıyordu.
   Şimdi ilk index listesi de boş; geometri doldurulduktan sonra indexler atanır.
   Kivy 2.3.1 `Mesh.build()` sıfır vertex/index durumunu atladığı için eski ilk
   durumun tek başına GPU çökmesini kanıtlamadığını özellikle belirtmek gerekir.
2. `MatchScreen.dispose()` boyut/konum bağlarını kaldırmıyordu. Eski maç ekranına
   gelen bir yerleşim çağrısı `draw_scene()` üzerinden temizlenmiş efekt Mesh'lerini
   yeniden doldurabiliyordu. Şimdi bağlar kaldırılıyor; kapatılmış ekranın layout
   ve arena çizim metotları işlem yapmıyor. İptal edilen ekran güncellemesi ve ilk
   frame callback'i de kaldırılıyor; dispose tekrar çağrılabilir.
3. Normal başlangıç yollarında farklı thread üzerinde Canvas erişimi saptanmadı.
   Yine de router başlangıç sınırı artık oluşturulduğu Kivy thread'ini kontrol
   ediyor. Farklı thread isteği Clock'a aktarılır; kapanış bekleyen istekleri iptal
   eder. Bu koruma mevcut çökmede thread ihlali bulunduğu anlamına gelmez.

FBO thumbnail'ları önbellekte texture referanslarıyla, maç görselleri kendi
Mesh/Texture/region referanslarıyla tutuluyor. Eski ekranın Canvas'ı yeni maç
ekranına aktarılmıyor. Grafik nesnelerinde yeni bir ortak cache/renderer kurulmadı.
Fire/Electric shader'ları, parçacık sayıları ve animasyon algoritmaları korundu.
Kullanıcı verileri ve fizik/ses/gol/kart kodları değiştirilmedi.

## Teşhis logları

Logcat içinde `SimomatchDiag` arayın. Thread adı/kimliği loglara eklenir:

- `MATCH_START_REQUESTED`: tema.
- `RECORDING_ENABLED`: 0/1 ve kayıt adaptörü daha önce oluşturulmuş mu.
- `RECORDING_PERMISSION_REQUESTED`: yalnızca kayıt açık yol.
- `RECORDING_PREPARED`: encoder hazırlığı sonrası.
- `ARENA_CANVAS_READY`: arena Canvas yapısı/geometrisi hazır; GPU çizimi henüz
  başarıyla tamamlandı anlamına gelmez. Tema/katman/efekt bilgisi içerir.
- `MATCH_SCREEN_CREATED`: maç ekranı constructor'ı tamamlandı.
- `MATCH_ANIMATION_STARTED`: render Clock güncellemesi planlandı.
- `MATCH_FIRST_FRAME_PRESENTED`: sonraki Window flip gerçekleşti.
- `MATCH_START_DISPATCHED_TO_KIVY`: başlangıç isteği başka thread'den geldi.

Örneğin Canvas hazır logu varken ilk frame logu yoksa çökme ilk çizim/flip
aralığına daralır. `RECORDING_ENABLED enabled=0` ve izin logu yoksa o denemede
MediaProjection başlatılmamıştır. Daha önce kullanılan adaptörün cache'de olması
aktif kayıt anlamına gelmez.

## APK test matrisi

Her denemede uygulamayı yeniden açın; tema, kayıt seçimi ve son başarılı
`SimomatchDiag` satırını kaydedin. Tam logcat/tombstone'u koruyun.

1. Kayıt kapalı, Rainbow Neon.
2. Kayıt kapalı, Fire Arena.
3. Kayıt kapalı, Electric Blue.
4. Kayıt açık, Rainbow Neon; izin onayı ve reddini ayrı deneyin.
5. Üst üste üç maç (eski Clock'ların durması / yeni izin oturumları).
6. Maç sonu sonuç ekranı (kayıt bitse de panelin açık kalması).

Windows otomatik testleri Mesh veri tutarlılığını, eski ekranın yeniden
çizilmemesini, thread aktarımını, kayıt kapalı izolasyonunu ve üç tema arasında
geçişi denetler. NVIDIA/Windows testi Adreno 750 / Android 16 SIGSEGV doğrulaması
değildir. Bu sürüm için "Android native crash kesin düzeldi" iddiası yoktur.

Son Windows koşusu: **482 test geçti**, 96,66 saniye. Yeni 8 regresyon testi
`tests/test_graphics_lifecycle.py` içindedir. Cihaz/ADB erişimi bulunmadığından
Android testi yapılmadı.

Bu incelemede değişen/eklenen dosyalar:

- `screens/arena_layers.py`
- `screens/match_screen.py`
- `screens/router.py`
- `services/video_recording.py` (yalnızca teşhis aşaması logları)
- `services/graphics_diagnostics.py`
- `tests/test_graphics_lifecycle.py`
- `docs/ANDROID_SIGSEGV.md`

Kivy 2.3.1 Mesh sıfır geometri kontrolü için incelenen kaynak:
https://github.com/kivy/kivy/blob/2.3.1/kivy/graphics/vertex_instructions.pyx
