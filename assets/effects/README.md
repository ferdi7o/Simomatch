# Arena efekt katmanları

Bu klasöre henüz gerçek alev/elektrik görselleri eklenmemiştir. Canvas renkleri,
glow ve parçacıklar yalnızca stilize neon efektleridir; gerçekçi alev veya yıldırım
yerine geçmez. Eksik dosyalar oyunu durdurmaz.

Tema tanımları `services/arena_themes.py` içindeki `SpriteLayer` verisini kullanır:

| Tema | İsteğe bağlı dosya | Düzen | Oynatım |
| --- | --- | --- | --- |
| Neon Purple | `neon_purple/ring.png` | 1 kare | Sabit doku |
| Fire Arena | `fire_arena/flames.webp` | 8 sütun × 1 satır | 20 FPS |
| Electric Blue | `electric_blue/lightning.webp` | 8 sütun × 1 satır | 18 FPS |
| Rainbow Neon | `rainbow_neon/ring.png` | 1 kare | 12°/s dekoratif dönüş |
| Emerald Arena | `emerald_arena/energy.webp` | 8 sütun × 1 satır | 16 FPS |

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
- WebP çözme desteği kullanılan Kivy görüntü sağlayıcısına bağlıdır; destek
  yoksa dosya atlanır. PNG atlası alternatif olarak tanımlanabilir.
