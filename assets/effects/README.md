# Arena efekt katmanları

Üç hazır RGBA halka görseli `assets/arena_effects/` içinden yüklenir. Bunlar tek
karelik görsellerdir: parlaklık değişimi, hafif dönüş ve sınırlı parçacıklarla
desteklenir; gerçek kare kare alev hareketi üretmez. Eksik dosyalar oyunu durdurmaz.

Tema tanımları `services/arena_themes.py` içindeki `SpriteLayer` verisini kullanır:

| Tema | İsteğe bağlı dosya | Düzen | Oynatım |
| --- | --- | --- | --- |
| Neon Purple | `assets/effects/neon_purple/ring.png` | 1 kare, henüz yok | Canvas neon yedeği |
| Fire Arena | `assets/arena_effects/fire_arena.png` | 1 kare | 18 saniyede bir tur + 60 dinamik alev + 12 hareketli kıvılcım |
| Electric Blue | `assets/arena_effects/electric_blue.png` | 1 kare | 12 saniyede bir tur + kısa parlamalar + mavi parçacıklar |
| Rainbow Neon | `assets/arena_effects/rainbow_neon.png` | 1 kare | 6°/s dekoratif dönüş |
| Emerald Arena | `assets/effects/emerald_arena/energy.webp` | 8 sütun × 1 satır, henüz yok | Canvas enerji yedeği |

1254×1254 kaynakların şeffaf boşlukları farklıdır. `source_radius_pixels` ve
`source_center_pixels`, parlak halka çekirdeğini fiziksel çembere eşlemek için
ölçülmüş kaynak-piksel kalibrasyonlarıdır. Merkez sol-üst başlangıçlıdır. X ve Y
aynı piksel ölçeğini kullanır; resim esnetilmez. Kaynak PNG dosyaları değiştirilmez.
Halka şeklindeki Mesh, kale açısı ± açıklık yarı açısı arasındaki dilimi hiç
üretmez. Böylece tüm alfa/parlama katmanı aynı hareketli boşluğa sahiptir; siyah
bir kapatma şekli çizilmez. Direkler, file ve takım diskleri daha sonra çizilir.

- Her hücre şeffaf arka planlı, merkezlenmiş tam halka efekti içermelidir.
  Kare sırası soldan sağa, ardından üstten alta gider. Kare boyutları eşittir.
- PNG veya atlas olarak kaydedilmiş WebP kullanılır. Animasyonlu WebP'nin kendi
  zaman çizgisi kullanılmaz; kareler `columns`, `rows`, `frames`, `fps` ile seçilir.
- Doku çizimi güncel fiziksel arena merkezi/yarıçapından türetilir. Kale aralığı
  her karede Mesh geometrisinden çıkarılır; görsel kale ağzını kapatmaz.
- En fazla 3 katman, katman başına 64 kare, atlas başına 4 megapiksel ve
  4096 piksel kenar sınırı vardır. 8 × 256 piksel gibi küçük atlaslar tercih edin.
- Katmanlar bir defa yüklenir; animasyon sırasında dosya okuma yapılmaz.
  Dekoratif dönüş ve FPS fizik/kale hızından bağımsızdır.
- Fire Arena 20°/s, Electric Blue -30°/s, Rainbow Neon önceki gibi 6°/s döner.
  Tek PNG'deki desen döndürülür; gerçek kare kare alev/yıldırım animasyonu değildir.
  Elektrik parlaması yereldir, 0,16 saniyede kaybolur. Parlamalar ve parçacıklar
  sırasıyla 8 ve 48 öğelik mevcut havuzlarla sınırlıdır; varsayılan ortam üretimi
  saniyede yaklaşık 3 kıvılcım veya 0,7 parlama + 2 mavi parçacıktır.
- WebP çözme desteği kullanılan Kivy görüntü sağlayıcısına bağlıdır; destek
  yoksa dosya atlanır. PNG atlası alternatif olarak tanımlanabilir.
- Electric Blue PNG dönüşünden bağımsız olarak en fazla 6 prosedürel yıldırım ve
  24 enerji parçacığı üretir. 5–9 ana parçalı çapraz kollar ve iki yönde ilerleyen
  15–45 derecelik yaylar kullanılır; ömürleri 0,15–0,4 saniyedir. Çizgiler 2,5 kat
  kalınlaştırılmış mavi glow, cyan gövde ve beyaz çekirdek katmanlarıyla PNG üstünde
  çizilir. Tek Mesh ve yeniden kullanılan havuzlar kullanılır.
  Çekirdek, glow ve parçacık üçgenleri güncel kale açıklığından kırpılır.
  Yeni bitmap veya sprite dosyası gerekmez; mevcut PNG değiştirilmez.
