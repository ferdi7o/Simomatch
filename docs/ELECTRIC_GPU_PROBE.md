# Electric Blue ilk kare GPU incelemesi

Yeni cihaz logları kayıt kapalı/adaptör oluşturulmamış yolun Canvas constructor'ını
tamamladığını, fakat sonraki Window flip loguna ulaşamadığını gösteriyor. Sorun
ilk çizim/flip aralığında. Bu kayıt motorunu bu denemeden eler; **hangi grafik
talimatının Adreno sürücüsünü düşürdüğünü henüz kanıtlamaz**.

## Kod incelemesi ve değişiklik

- Elektrik RenderContext'i iki float konum + dört float RGBA (24 bayt/vertex)
  kullanıyor. Mesh ve shader Canvas içinde, PNG texture bölgeleri `frames`
  tuple'ında tutuluyor. İncelenen yolda erken serbest bırakılan bir nesne veya
  kanıtlanmış hatalı vertex/index bulunmadı. Android context kaybı burada
  yeniden üretilemedi.
- Elektrik ve raster arena Mesh'leri için ortak, küçük bir CPU doğrulama sınırı
  eklendi: stride, float32 sonluluğu/taşması, üçgen index sayısı, GLES2 boyutları
  ve indexlerin vertex sınırları kontrol edilir. UV'ler de sonlu olmalıdır.
- Kasıtlı/geçersiz veri testlerinde GPU nesnesine hiç yazılmaz; son geçerli
  geometri korunur ve `MESH_REJECTED` yazılır. Normal ilk karelerde malformed
  geometri bulunduğu iddiası yoktur.
- Güncelleme sırası artık `indices=[] -> vertices=... -> indices=...` şeklinde.
  Eski indexler daha kısa yeni vertex listesine geçici olarak bile işaret etmez.
  Normal Kivy akışında aynı thread'deki bu atamalar arasında render olmadığından
  eski sıranın bu cihaz SIGSEGV'sini tetiklediği kanıtlanmış değildir.
- Root router'ın önceki Kivy thread kontrolü korunuyor. Ayrıca Mesh oluşturulduğu
  thread dışından draw/clear/arena layout çağrıları grafik nesnesine erişmeden
  durdurulur. Bu yolda mevcut bir thread ihlali saptandığı anlamına gelmez.
- Önceki dispose/Clock temizliği korundu. Video, Fire parçacıkları, fizik ve
  kullanıcı kayıt kodları değiştirilmedi. Normal renk/kalınlık/sıklık/şekil,
  kale maskelemesi ve çizim sırası korunuyor.

## Kontrollü APK karşılaştırması

`assets/electric_gpu_probe.json` dosyasındaki `mode` değerini değiştirip APK'yi
yeniden derleyin. Bu bir kullanıcı ayarı değildir ve takım kayıtlarına yazılmaz.
Eksik/bozuk dosya veya bilinmeyen değer `full` davranışına döner.
Varsayılan ve teslim edilen değer **full**. Modlar sadece Electric Blue'yu etkiler.

| mode | Sınanan yol |
| --- | --- |
| `full` | Mevcut PNG + tam elektrik dalgaları/yıldırımları/parçacıkları |
| `png_only` | Elektrik RenderContext'i çizim ağacına bağlanmaz; PNG ve diğer maç çizimleri kalır. Elektrik nesnesi hâlâ oluşturulur ve geometri hesaplanır. |
| `triangle` | Aynı elektrik RenderContext/shader/vertex formatı, tek geçerli cyan üçgen. PNG kalır. |
| `no_png` | Yalnızca Electric Blue'nun PNG katmanı çıkar; tam elektrik ve Canvas arena kalır. |
| `deferred` | İlk flip PNG ile yapılır; tam elektrik sonraki kare için, aynı katman sırasındaki gruba eklenir. |

Her denemede kayıt **kapalı** olsun; uygulamayı tamamen kapatıp açın. Aynı
takımlar/arka plan/ayarlar ile şu sırayı izleyin: `full`, `png_only`, `triangle`,
`no_png`, `deferred`. Sonra yapılandırmayı `full` olarak geri alın.

- `png_only` geçip `triangle` düşerse custom RenderContext/shader/format yolu
  şüphelidir; dalga karmaşıklığı tek başına açıklama olmaz.
- `triangle` geçip `full` düşerse gerçek batch büyüklüğü veya dinamik veri/
  driver davranışı daha güçlü adaydır; bu hâlâ tek başına kesin kök neden değildir.
- `no_png` geçip `png_only` düşerse raster/texture yolu öncelikli incelenir.
- `deferred` önce `MATCH_FIRST_FRAME_PRESENTED`, sonra
  `ELECTRIC_DEFERRED_ATTACHED` yazıp düşerse sonraki elektrik ekleme/çizim yolu daralır.
- Tüm sade modlar düşerse log/stack ile diğer arena/HUD çizimleri ve context
  durumuna geri dönülür; yalnızca elektrik suçlanmaz.

Bu sonuçlar yük/zamanlama farklarından da etkilenebilir. Bir modun geçmesi,
özelliği kalıcı kapatarak sorunun çözüldüğü anlamına gelmez.

## İstenen loglar ve cihaz kontrolleri

`SimomatchDiag` satırlarını SIGSEGV/tombstone ile birlikte saklayın:

- `ELECTRIC_PROBE_MODE mode=...`
- `ELECTRIC_SHADER_READY success=...`
- `MESH_VALIDATED mesh=electric/arena_raster`: ilk dört başarılı yüklemede vertex,
  index, stride, max index, thread/kimlik bilgisi
- `MESH_REJECTED`: reddedilen veri ve nedeni
- Önceki `ARENA_CANVAS_READY`, `MATCH_SCREEN_CREATED`, `MATCH_FIRST_FRAME_PRESENTED`

Normal `full` modunda ayrıca Fire/Rainbow maçları, üç ardışık maç, maç sonu ve
hareketli kalenin açıklığını kontrol edin. Sıklık/ışık/glow ve logo/kale katman
sırası öncekiyle aynı kalmalıdır. Android'deki CPU/FPS maliyetini de ölçün;
her batch doğrulaması maliyetlidir ve Windows süresi Android ölçümü değildir.

Windows testleri bozuk batch reddini, sıralı yüklemeyi, owner-thread kontrolünü,
üç çözünürlükte ilk/animasyon karelerini, beş test modunu, mevcut GPU piksel/maske
testlerini kapsar. NVIDIA üzerindeki başarı Adreno 750 sürücüsünü doğrulamaz.
Android cihaz/ADB erişimi olmadığından bu sürümün cihazdaki SIGSEGV'yi giderdiği
iddia edilmiyor.

Son doğrulama: Windows Python 3.10.9 / Kivy 2.3.1 üzerinde **506 test geçti**
(109,51 saniye). Yeni güvenlik/izolasyon dosyası 24 test senaryosu içerir. Mevcut
elektrik glow/renk/kale açıklığı GPU piksel testleri de tam koşuda geçti.

Değişen/eklenen dosyalar: `screens/electric_effects.py`, `screens/arena_layers.py`,
`screens/match_screen.py`, `screens/mesh_safety.py`, `assets/electric_gpu_probe.json`,
`tests/test_electric_mesh_safety.py`, `docs/ELECTRIC_GPU_PROBE.md`.

İncelenen Kivy 2.3.1 Mesh kaynağı:
https://github.com/kivy/kivy/blob/2.3.1/kivy/graphics/vertex_instructions.pyx
