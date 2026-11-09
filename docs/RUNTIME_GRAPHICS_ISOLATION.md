# Fire / Electric — aynı APK içinde kontrollü GPU izolasyonu

Bu değişiklik bir SIGSEGV düzeltmesi değildir. Android 16 / Adreno 750'de hangi bileşenin çökmeyi tetiklediğini saptamak için test altyapısıdır. Efektler silinmedi, shader değiştirilmedi, mevcut üretim renderer'ı değiştirilmedi. Fizik/gol/kart/ses/video koduna bu görevde müdahale edilmedi.

## Oyun içinde kullanım

1. Yeni kaynaklarla APK'yi bir kez derle ve yükle.
2. MAÇ OLUŞTUR ekranında Fire Arena veya Electric Blue seç.
3. ARENA TEMASI galerisinin hemen altındaki **GPU Teşhis Modu** düğmesine bas.
4. İlk test dizisi için EFEKT YOLU değerini **auto** bırak. MODE düğmelerinden birini seç. Seçim hemen kaydedilir ve sonraki maçta uygulanır.
5. MAÇI BAŞLAT. Uygulama çökerse tekrar aç, aynı düğmeden farklı MODE seç. APK yeniden oluşturulmaz.
6. Her temada MODE 0, 1, 2, 3 ve 4'ü ayrı maçlarla dene. Önce kayıt kapalı test et; çalışan/çöken modu kaydet.
7. İşin bitince **TEŞHİSİ KAPAT - MEVCUT ÇİZİM** seç. Bu, MODE 4'ten farklı olarak eski paket içi teşhis ayarları dahil önceki akışı olduğu gibi kullanır.

Fire ve Electric tercihleri bağımsızdır. Seçim `App.user_data_dir` kökünden router'a geçirilen kalıcı dizinde ayrı `graphics_probe.json` dosyasına atomik yazılır. Bu dosya yalnızca geliştirici teşhis tercihidir; takım ve maç ayarları JSON'ları değiştirilmez. Normal/Rainbow temalarında düğme devre dışıdır ve hiçbir mod uygulanmaz. Kayıt dosyası eksik/bozuksa teşhis varsayılan olarak kapalıdır.

## Bileşen matrisi

| Mod | PNG yolu | Ortak arena_raster Mesh | Fire/Electric efekti | Ek tema ortam parçacıkları |
| --- | --- | --- | --- | --- |
| 0 BASE ONLY | Yok | Yok | Yok | Yok |
| 1 IMAGE ONLY | Standart Kivy Image | Yok | Yok | Yok |
| 2 IMAGE + RASTER | Mevcut arena_raster | Var | Yok | Yok |
| 3 IMAGE + EFFECT | Standart Kivy Image | Yok | Var | Yok |
| 4 FULL | Mevcut arena_raster | Var | Var | Mevcut tam davranış |

Kod incelemesi: PNG zaten `arena_raster` tarafından texture olarak çiziliyor. MODE 2 ve 4'te aynı PNG ikinci kez üstüne çizilmez; IMAGE bileşeninin çizicisi arena_raster'dır. MODE 1 ve 3'te aynı dosya/kalibrasyon, standart Kivy Image widget'ıyla çizilir. Widget match Canvas bağlamı dışında oluşturulur ve kendi Canvas'ı bir kez, takım logoları ve kalenin arkasına eklenir. Böylece PNG kaynağı ile ortak Mesh yolunun farkı izole edilir.

MODE 0–3 normal temel sahneyi kullanır; ortak neon sınır, takım logoları, skor ve kale kalır. Mode 0–3'te MatchEffects'in çizim talimatları/parçacık havuzları da oluşturulmaz. Normal tema ve Rainbow'un üretim çizimi değişmedi. Arena merkezi, fiziksel yarıçapı, gol çizgisi/direkleri ve maç parametreleri bütün modlarda aynıdır.

**MODE 1/3 bilinçli olarak kale maskesiz ve hareketsiz referans PNG kullanır.** Statik halka kale açıklığının üstünde görünebilir; bu sadece geçici teşhis görüntüsüdür, gol fiziğini değiştirmez. Elle FBO veya ek stencil maskesi oluşturulmaz. Standart Kivy Image'ın kendi dahili KV Canvas/stencil talimatları vardır. MODE 2/4'te mevcut dönen açıklık/maskeleme çalışmaya devam eder. MODE 3'ün Fire/Electric parçacıkları mevcut fiziksel açıklığa göre kırpılır.

"Shader yok" ifadesi özel shader/RenderContext yok demektir: Kivy/OpenGL ES standart Image ve temel sahneyi de stok shader ve dahili VertexInstruction/VBO ile çizer. MODE 0 sıfır OpenGL değildir; ek arena Mesh'i veya özel shader oluşturmaz.

## Efekt yolunu ayrıca izole etme

Panelde EFEKT YOLU düğmesi sırayla şu değerleri seçer; ardından MODE 3 veya 4'e basarak kaydet:

- auto: mevcut platform varsayılanı (Android texture, Windows custom).
- texture: mevcut standart shader / RGBA atlas renderer'ı.
- custom: mevcut özel RenderContext / renk attribute'lu shader.
- flat_probe: aynı parçacık geometrisi, standart shader ve düz renk; renk/fade kalitesi bilinçli olarak teşhis içindir.

Bu seçenekler efekt sıklığını, geometrisini veya fizik motorunu değiştirmez. Özellikle custom yolu Android'de yeniden çökebilir; amaç bu yolu ayrı sınamaktır. Efekt yolu MODE 0/1/2'de efekt oluşturmaz. Varsayılan test dizisinde auto'yu sabit tutarak bir seferde tek değişkeni değiştir.

Aktif runtime MODE; `assets/arena_gpu_probe.json` içindeki raster/fire/electric/custom_shader/trace ve `assets/electric_gpu_probe.json` kısıtlamalarından önceliklidir. Böylece eski bir `no_png`, `png_only` veya kapalı raster anahtarı test matrisini sessizce bozmaz. Teşhis kapalıyken eski ayarlar aynen geçerlidir.

## Logları alma ve yorumlama

```bash
adb logcat -c
adb logcat -v threadtime > simomatch_graphics.txt
```

İkinci komut açıkken bir MODE test et, sonra Ctrl+C ile dosyayı kapat. Native crash satırları da dahil tam dosyayı koru; sadece filtrelenmiş logu almak tombstone/backtrace'i kaybettirebilir. Aynı APK'de diğer modla tekrar et.

Başlıca SimomatchDiag olayları:

- `GRAPHICS_PROBE theme=... mode=... image=... common=... effect=... renderer=...`: fiilen istenen bileşen matrisi, thread/owner kimliği.
- `ARENA_GPU_PROBE source=runtime theme=... mode=... image=... raster=... fire=... electric=... custom_shader=... renderer=... trace=True`: runtime modun etkin bayrakları. BASE/IMAGE ONLY'de raster/fire/electric/custom_shader hepsi False olur. `source=asset_json mode=disabled` ise runtime mod seçilmemiştir (veya tema desteklenmiyordur); paket içi eski varsayılanlar kullanılıyordur. trace=False tek başına APK sürümünü kanıtlamaz.
- `GRAPHICS_EFFECT_CREATE_BEGIN`, `GRAPHICS_EFFECT_READY` / `GRAPHICS_EFFECT_SKIPPED`: efekt constructor ve Canvas türü, özel shader durumu.
- `GRAPHICS_IMAGE_CREATE_BEGIN`, `GRAPHICS_IMAGE_READY` / `GRAPHICS_IMAGE_REJECTED`: PNG yolu, KivyImage/raster çizicisi ve kale maskesi durumu.
- `GRAPHICS_COMMON_CREATE_BEGIN`, `GRAPHICS_COMMON_READY`: ortak Mesh oluşturma, gerçek yüklenen katman sayısı.
- `GRAPHICS_LAYOUT_BEGIN`, `GRAPHICS_TEXTURE_CHECK`, `GRAPHICS_CONTEXT_CHECK`, `GRAPHICS_MESH_CHECK`, `GRAPHICS_LAYOUT_READY`: ilk CPU yerleşimi, boyutlar/UV, güçlü nesne referansları, vertex/index/stride kontrolü. Shader success derleyici durumudur; GPU yürütmesinin güvenli olduğunu kanıtlamaz.
- `GRAPHICS_CANVAS_GPU_ENTER/EXIT`, `GRAPHICS_IMAGE_GPU_ENTER/EXIT`, `RASTER_GPU_ENTER/EXIT`, `FIRE_CONTEXT_GPU_ENTER/EXIT`, `ELECTRIC_CONTEXT_GPU_ENTER/EXIT`: çizim sırası içindeki tek seferlik Callback işaretleri. Bunlar GL state değiştirmez.
- `GRAPHICS_FIRST_UPDATE`: ilk Clock güncellemesi.
- `GRAPHICS_FIRST_FRAME`: mevcut Window `on_flip` sınırına ulaşıldı. Bu Android compositor'ın fiziksel ekrana sunduğuna dair ayrı bir onay değildir.
- `GRAPHICS_THREAD_REJECTED`, `MESH_REJECTED`, `GRAPHICS_AUDIT_REJECTED`: çizim verisi/thread ihlali. Hatalı CPU verisi başarılı sayılmaz.
- `GRAPHICS_DISPOSE`: eski görünümün iptal/temizleme yolu.

GPU işaretleri asenkron sürücü işini veya compiler'ın komut gruplamasını tek tek GL çağrılarına eşlemez; son işaret tek başına kesin kök neden değildir. Örneğin MODE 1 çalışıp MODE 2 çökerse ortak raster yolu güçlü aday olur; MODE 3 de çökerse efekt yolu ayrıca araştırılmalıdır. MODE 0 çökerse yalnız özel PNG/efekt suçlanamaz. MODE 4'ün tek başına çökmesi bileşen etkileşimine işaret eder. Bulguları native backtrace ile birlikte değerlendir.

## Güvenlik ve host testleri

MeshGuard mevcut bütün upload'larda float32 sınırı/NaN/Infinity, vertex stride, üçgen/index sınırlarını denetlemeye devam eder. Runtime probede ilk tam yerleşimde kaynak texture boyutları/UV'ler ve fiili Mesh içerikleri ayrıca denetlenir. Texture GL id'sine teşhis için erişilmez; bu erişim kendisi lazy allocation tetikleyebilir. Referans PNG ve raster kaynak texture'ları görünüm ömrü boyunca tutulur. MatchScreen layout/draw/update/dispose ve ilk flip sahip thread'inde olmalıdır; router'ın mevcut Kivy thread'e dispatch'i korunmuştur. Eski Clock ve flip callback iptalleri korunmuştur.

Yeni Windows testleri: on mod/tema kombinasyonunu FBO'da çizme, efekt renderer seçenekleri, seçim kalıcılığı/atomik yazma hatası, eksik veya geçersiz texture, geometri merkez/ölçek korunması, thread reddi, ardışık maç değişimi, dialog temizliği ve 320×640 / 450×800 / 720×1280 / 1080×1920 kontrolleri. Bunlar Android GPU testinin yerine geçmez.

Güncel doğrulama: tam paket `python -m pytest -q`: **618 geçti, 131,22 saniye**. Paket 45 runtime teşhis testi içerir. BASE/IMAGE ONLY'de Mesh ve özel RenderContext constructor'larının çağrılmadığı, runtime bayraklarının kapalı loglandığı ve standart Kivy Image'ın texture'ı gerçekten çizdiği ayrıca test edildi. Android APK/GPU testi bu ortamda yapılmadı; SIGSEGV'nin giderildiği veya kök nedeninin bulunduğu iddia edilmiyor.
