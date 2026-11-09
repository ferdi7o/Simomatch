# İki Android sorunu: ortak arena çizimi ve CaptureService paketlemesi

## 1. Arena SIGSEGV

### Bulunan kök neden

**Native çöküşün kesin tetikleyicisi henüz kanıtlanmadı.** Normal modelin
çalışması ve Rainbow dahil raster katmanlı temaların çökmesi ortak raster/
texture/VBO yolunu öncelikli aday yapıyor. Bu, elektrik Mesh'i veya GPU sürücüsü
tek başına suçlu demek değildir. Bu projede Neon/Emerald efekt dosyaları eksik,
Fire/Electric/Rainbow PNG'leri mevcut: normal yolda raster katman yüklenmezken
bu üç temada yüklenir. Standart Kivy şekilleri de VBO kullandığı için
"normal temada hiç VBO yok" sonucu çıkarılamaz.

Raster geometrisi: 194 vertex, 576 üçgen indexi, en büyük index 193;
her vertex `x,y,u,v`, dört float / 16 bayt. UV dönüşümü şeffaf marj kalibrasyonu,
dönüş ve fiziksel kale açıklığına göre hesaplanır; 0..1 dışındaki UV'ler tek
başına geçersiz OpenGL verisi değildir. MESH_VALIDATED yalnızca CPU verisini
kontrol eder; gerçek GL buffer binding, context durumu veya driver yürütmesini
doğrulayamaz.

### Değiştirilen dosyalar

- `screens/arena_layers.py`: açık vertex formatı, texture sahipliği, isteğe bağlı draw sınırı logları.
- `screens/fire_particles.py`, `screens/electric_effects.py`: normal renderer korunarak stock-shader teşhis seçeneği.
- `screens/mesh_safety.py`: renkli geometriyi teşhis amaçlı standart formata aktarma; Fire'a da doğrulama uygulanır.
- `screens/match_screen.py`: ortak raster/efekt/shader seçeneklerini bağlar; fizik, gol ve sonuç ekranı mantığı değişmez.
- `services/arena_gpu_probe.py`, `assets/arena_gpu_probe.json`: kontrollü teşhis yapılandırması.
- `tests/test_common_arena_probe.py`: bağımsız anahtarlar, gerçek GPU çizimi ve GC sonrası texture sahipliği.

### Yapılan düzeltme

Raster Mesh artık örtük format yerine açık `vPosition(2), vTexCoords0(2)`
formatıyla kendi VBO düzenini kurar. Kaynak Texture referansı da açıkça tutulur.
Bu değişikliklerin tek başına telefondaki çöküşü giderdiği iddia edilmiyor.
Shader, renkler, kalibrasyon ve efekt algoritmaları normal modda korunur.

`assets/arena_gpu_probe.json` varsayılanı:

```json
{"raster":true,"fire":true,"electric":true,"custom_shader":true,"trace":false}
```

Teşhis APK'leri için yalnızca ilgili alanı değiştirin, tekrar derleyin:

| Karşılaştırma | Ayarlar |
| --- | --- |
| Normal görünüm + log | Hepsi true, trace true |
| Ortak raster kapalı | raster false; diğerleri true |
| Yalnız raster (özel parçacık yok) | raster true, fire false, electric false |
| Özel shader kapalı, aynı parçacık geometrisi | custom_shader false; raster/fire/electric true |

`custom_shader=false` sadece teşhistir: normal Kivy Canvas/shader/UV formatı
kullanır, parçacıklar tek bir düz tint ile görünür. Glow/vertex alpha renkleri
bu modda normal kaliteyi temsil etmez. Üretim seçeneği değildir. Tam görünümü
geri getirmek için bütün özellikleri true, trace'i false yapın.

Eski `assets/electric_gpu_probe.json` dosyasını bu karşılaştırmalarda `full`
bırakın; eski Electric-only modlar hâlâ desteklenir. Ortak ayarlar kullanıcı
kayıtlarına yazılmaz ve eksik/bozuk dosya normal görünüme geri döner.

`trace=true` ilk GPU yürütmesinde şu çiftleri loglar:

- `RASTER_GPU_ENTER` / `RASTER_GPU_EXIT` (texture bağlama + raster Mesh bloğu).
- `FIRE_CONTEXT_GPU_ENTER/EXIT`, `ELECTRIC_CONTEXT_GPU_ENTER/EXIT` (context geçişi dahil).
- `FIRE_MESH_GPU_ENTER/EXIT`, `ELECTRIC_MESH_GPU_ENTER/EXIT` (context içindeki Mesh).

Bir ENTER olup EXIT olmaması aralığı daraltır; tek başına sürücü kök nedenini
kanıtlamaz. Callback'ler GL durumuna dokunmaz; varsayılan modda oluşturulmazlar.

### Android üzerinde hâlâ doğrulanması gerekenler

Raster kapalıyken üç özel tema da çalışırsa ortak katman önceliği güçlenir.
Raster-only de çökerse custom shader/parçacıklardan bağımsız bir yol gösterir.
Stock shader probe'u çalışırsa custom format/context yolu ayrıca incelenir.
Son başarılı ENTER/EXIT ve tam tombstone birlikte değerlendirilmelidir.
Windows/NVIDIA başarısı Adreno 750 / Android 16 başarısı değildir.

## 2. CaptureService ClassNotFoundException

### Bulunan kök neden

Runtime'ın `org.simomatch.capture.CaptureService` sınıfını yükleyemediği kesin.
Windows deposunda kaynak yolu ve isimler doğru:

- Kaynak: `android_src/org/simomatch/capture/CaptureService.java`.
- Java package: `org.simomatch.capture`.
- Python: `autoclass('org.simomatch.capture.CaptureService')`.
- Manifest servis adı aynı; `exported=false`, `foregroundServiceType=mediaProjection`.

App applicationId'nin farklı olması bu tam nitelikli Java adını yanlış yapmaz.
WSL spec'inin rsync dışında tutulması nedeniyle Windows'taki Java derleme
ayarlarının WSL'ye ulaşmaması güçlü açıklamadır. **Gerçek WSL spec ve hatalı APK
DEX'i görülmeden bu aktarım hatası kesin kök neden diye raporlanamaz.**
Bu ortamda WSL dağıtımlarını listeleme E_ACCESSDENIED döndürdü; Android SDK/APK
derlemesi ve gerçek sınıf yüklemesi doğrulanamadı.

### Değiştirilen dosyalar

- `buildozer.spec`: Java/AAR ayarlarının gerçek WSL spec'e taşınması gerektiği açıkça belirtildi.
- `tools/check_android_capture.py`: kaynak/spec kontrolü, yedekli/atomik WSL spec güncellemesi, APK DEX tanımı kontrolü.
- `services/video_recording.py`: gerçek autoclass başarısından sonra CAPTURE_SERVICE_CLASS_LOADED logu.
- `tests/test_android_capture_packaging.py`: WSL ayarlarını koruma, package uyumu, multidex ve yalnız string/reference içeren sahte başarıyı reddetme.

### Yapılan düzeltme

Windows spec'indeki kalıcı ayarlar doğrudur; WSL tarafındaki **gerçek kullanılan**
spec de bunları almalıdır. Sadece Java dosyasını Python asset'ine kopyalamak
derleme değildir. `capture_manifest.aar` bilerek yalnızca manifest içerir;
CaptureService'in derlenmesi `android.add_src` üzerinden sağlanır.

Gerekli ayarlar (mevcut izin, ABI ve requirements girdilerinizi silmeden):

```ini
android.api = 36
android.archs = arm64-v8a
android.permissions = FOREGROUND_SERVICE, FOREGROUND_SERVICE_MEDIA_PROJECTION
android.add_src = android_src
android.add_aars = android_src/capture_manifest.aar
android.add_gradle_repositories = flatDir { dirs 'libs' }
android.add_compile_options = "sourceCompatibility = 1.8", "targetCompatibility = 1.8"
```

`requirements` içinde `pyjnius` da olmalıdır. Güncelleme aracı mevcut Java 17
gibi compile seçeneklerini, sürümleri, NDK/SDK yollarını ve diğer ayarları korur.
`android_src/` (Java + AAR + XML), services/screens/assets ve yeni araçlar WSL
projesine kopyalanmalıdır; yalnız main.py kopyalamak yeterli değildir.

WSL proje klasöründe:

```bash
python3 tools/check_android_capture.py --apply --spec buildozer.spec
buildozer -v android debug
python3 tools/check_android_capture.py --spec buildozer.spec --apk bin/GERCEK_YENI_APK_ADI.apk
```

İlk komut orijinal spec'i `.capture-backup-...` uzantısıyla yedekler ve yalnızca
gerekli anahtarları günceller. Java kaynağı/package/manifest eksikse yazmadan
durur. Araç hiçbir Android cihaz dosyasını veya kullanıcı kaydını silmez.

Son komut `classes*.dex` içindeki **class_defs** tablosunu çözüp sınıf tanımını
arar. Yalnızca class adına ait string veya type reference bulunması başarı
sayılmaz. Başarı: `CAPTURE_CLASS_DEFINED_IN_DEX classes....dex`.
DEX 035..040 desteklenir; farklı sürümde SDK `apkanalyzer` kullanılmalıdır.
Bu kontrol APK imzası veya çalışabilirlik doğrulaması değildir.

APK manifestini SDK aracıyla ayrıca kontrol edin:

```bash
apkanalyzer manifest print bin/GERCEK_YENI_APK_ADI.apk
apkanalyzer dex packages --defined-only bin/GERCEK_YENI_APK_ADI.apk
```

Eski APK'yi yanlışlıkla kurmayın. Aynı applicationId/imza ile `adb install -r`
kullanıcı verilerini koruyarak günceller; bu iş için uninstall/pm clear kullanmayın.
Kaynak/spec doğru ama DEX eksikse derleme logunu inceleyin; gerekirse yalnız
proje derleme önbelleğini temizleyerek yeniden derleyin, telefon verilerini değil.

### Android üzerinde hâlâ doğrulanması gerekenler

DEX tanımı görüldükten sonra cihaz logunda `CAPTURE_SERVICE_CLASS_LOADED`
gelmeli; bu log yalnızca gerçek autoclass başarısından sonra yazılır.
Ardından yeni izin, foreground service, encoder hazırlığı, ilk kare ve
MediaStore finalize akışı sınanmalı. Source/spec kontrolü bunları doğrulamaz.

## İstenen APK test sırası

1. Normal tema, kayıt kapalı.
2. Fire Arena, kayıt kapalı.
3. Electric Blue, kayıt kapalı.
4. Rainbow Neon, kayıt kapalı.
5. Normal tema, kayıt açık (önce APK DEX kontrolü ve sınıf yükleme logu).
6. Sonuç ekranı sonrasında MP4 finalize, Galeri'de açılma; bu sürümün videoları sessizdir.

İlk dört aşama için tam görünüm ile başlayın. Çökerse yukarıdaki bağımsız
probe ayarlarıyla karşılaştırın; kapalı efektle geçen denemeyi kalıcı çözüm saymayın.

## Windows doğrulaması

Python 3.10.9 / Kivy 2.3.1 ile **533 test geçti** (115,65 saniye).
Kaynak/package/autoclass/manifest/Windows spec kontrolü başarılı. WSL spec
güncellemesi ve APK sınıf tanımı denetimi testleri izole test dosyalarıyla
çalıştırıldı; gerçek kullanıcı APK'sinin DEX'i incelenmedi. Native Android
derlemesi, cihaz sınıf yüklemesi, özel temaların Adreno çizimi ve MP4 çıktısı
burada doğrulanmadı. Fizik/gol motoru, maç sonu paneli ve kullanıcı dosyaları
değiştirilmedi.

Kaynaklar:

- https://github.com/kivy/buildozer/blob/master/buildozer/targets/android.py (add_src/add_aars)
- https://source.android.com/docs/core/runtime/dex-format (class_defs / type_ids / string_ids)
- https://developer.android.com/media/grow/media-projection (foreground service ve yeni onay akışı)
