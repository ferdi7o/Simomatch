# Fire / Electric Android çizim yolu

## Bulgular ve sınır

Rainbow ve normal temanın cihazda çalışması, ortak arena_raster Mesh katmanının tek başına sebep olduğunu kanıtlamıyor. Fire ve Electric ise özel RenderContext, özel shader ve x/y/RGBA vertex biçimini paylaşıyor. Shader kaynaklarında açık bir OpenGL ES 2 dışı özellik bulunmadı. Eldeki native backtrace kesin hatalı GL çağrısını göstermiyor; sürücü hatası veya shader uyumsuzluğu kesinleşmiş değildir.

## Uygulanan uyumluluk yolu

Android varsayılanında Fire ve Electric, özel RenderContext yerine Kivy standart x/y/u/v Mesh ve RGBA texture kullanır. Windows varsayılanı mevcut renderer olarak kalır. Fizik, kayıt, ses, normal tema ve Rainbow çizimi değiştirilmedi.

ParticleTextureBatch mevcut üçgenleri ve renklerini alır. Her üçgenin renk geçişi küçük 2x2 RGBA atlas hücresine taşınır. Dördüncü köşe rengi C1+C2-C0 olarak hesaplanarak mevcut doğrusal renk geçişi korunur; renk aralığı yetmezse üçgen dört eşdeğer alt üçgene bölünür. Sadece RGBA8 yuvarlaması eklenir. Geometri, sıralama, glow ve fade korunur. Kale açıklığı mevcut geometri kırpmasında hesaplanmaya devam eder.

Atlas 128x128, 64 KiB; iki CPU hazırlık tamponu yeniden kullanılır. Widget veya texture her karede oluşturulmaz. Vertex/index/renk doğrulaması GPU yüklemesinden önce yapılır. Texture güçlü referansla tutulur; context reload observer CPU kopyasını geri yükler. Oluşturma/güncelleme mevcut Kivy akışında, yükleme ve reload thread guard ile yapılır.

Texture yükleme ve üçgen dönüştürme ek CPU maliyeti getirir. Android FPS ve termal yük henüz ölçülmedi. Masaüstü piksel testleri gerçek cihaz performans testi değildir.

## Bağımsız teşhis

assets/arena_gpu_probe.json içindeki fire_renderer ve electric_renderer ayrı ayrı auto / texture / custom olabilir. auto Android'de texture, masaüstünde custom seçer. Windows üzerinde texture zorlanarak görsel karşılaştırma yapılabilir. Android'de custom yalnızca eski yolu izole etmek içindir; bilinen çökme yeniden oluşabilir.

Mevcut fire/electric/raster ve custom_shader teşhis anahtarları korunmuştur. custom_shader=false eski tek renkli teşhis yoludur; yeni renkleri koruyan texture yolu değildir. Efektleri kapatmak kalıcı çözüm olarak kullanılmadı.

## APK kontrol sırası

1. Normal ve Rainbow, kayıt kapalı: önceki çalışan görünüm ve maç akışı.
2. Fire, kayıt kapalı: alevler, kıvılcımlar, fade, kale açıklığı.
3. Electric, kayıt kapalı: dalgalar, dış yıldırımlar, glow ve kale açıklığı.
4. Her tema ile üç ardışık maç, sonuç ekranı ve uygulamayı arka plana alıp geri dönme.
5. Fire ve Electric, kayıt açık: kayıt bağımsızlığı ve FPS.

Logda PARTICLE_RENDERER_READY effect=... renderer=texture custom_shader=False stride_bytes=16 ve MATCH_FIRST_FRAME_PRESENTED görülmeli. Native crash varsa yeni tam backtrace alınmalı. Cihaz testi olmadan SIGSEGV giderildiği söylenemez.

## Otomatik doğrulama

Yeni testler Android renderer seçimini, özel RenderContext'e girilmemesini, standart Mesh geçerliliğini, geçersiz veri reddini, context reload'u, thread kontrolünü ve tamponların tekrar kullanımını kapsar. Fire/Electric için üç ayrı kale açısında eski/yeni renderer FBO piksel karşılaştırmaları renk ve geometri korunmasını denetler.

Kivy texture API: https://kivy.org/doc/stable/api-kivy.graphics.texture.html
