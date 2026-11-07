# Simomatch — Aşama 2

Python 3.10 ve Kivy 2.3.1 ile takım oluşturma ve otomatik maç simülasyonu.

```powershell
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Testler: `python -m pytest -q`. Test çıktıları `.test_runtime/` altında tutulur.

Uygulama ana menüyle açılır. **TAKIM OLUŞTUR** ekranında en az iki takım
kaydedin, ardından **MAÇ OLUŞTUR** ekranında farklı takımları seçin. PNG/JPG logo
ve MP3 isteğe bağlıdır. Logo yoksa renkli disk ve kısa takım adı gösterilir.
Takım adı en fazla 40 karakterdir; boşluk ve büyük/küçük harf farkıyla aynı adı
tekrar kaydetmek engellenir. Takımlar düzenlenebilir ve silinebilir.

Windows'ta takım verileri proje içindeki `data/teams.json` ve `data/assets/` altında
tutulur; bu klasör kalıcıdır ve Git'e dahil edilmez. Android'de özel uygulama
veri dizini kullanılır. Kaydetme, medya dosyalarını benzersiz adlarla kopyalar ve
JSON'u atomik olarak değiştirir. Bozuk JSON değiştirilmeden önce yedeklenir.
Takım silinince medya dosyaları eski yedekleri bozmamak için korunur. Dosya başına
32 MB sınırı vardır. Bozuk/eksik logolar renkli diske geri döner. MP3 kayıtta
dosya başlığı düzeyinde denetlenir, maç öncesinde ses sağlayıcısıyla yüklenir.
Eksik/bozuk ses oyunu durdurmaz; ilgili ses sessizce atlanır.

Windows dosya seçicisi doğrudan Unicode Win32 API kullanır, Tcl/Tk gerektirmez.
Diğer masaüstlerinde Tk adaptörü bulunur. Android adaptörü Storage Access
Framework ile `content://` belgelerini özel `imports/` klasörüne alır; takım
kaydedildiğinde kalıcı `assets/` kopyası oluşturulur. Android uygulama etkinliği,
pyjnius/python-for-android entegrasyonu gerçek cihazda henüz doğrulanmamıştır.

Maç kurulumunda iki bağımsız logo/top yarıçapı (18–80 simülasyon birimi, varsayılan 60), süre
(10–600 saniye, varsayılan 55), bağımsız arena teması ve arka plan seçilir.
Kale dönüş hızı varsayılan 90°/s, ayar aralığı 30–180°/s'dir. Seçilen derece
değeri motorda saat yönünde radyan/saniyeye çevrilir ve yeniden başlatmada korunur.
Direk hızına göre uyarlanan fizik alt adımları yüksek dönüş hızında da çalışır.
Kale boyutu hız ayarının altındaki %60–150 kaydırıcısıyla seçilir (varsayılan %100).
Açıklığın kiriş genişliği seçilen yüzdeyle ölçeklenir; %100 önceki genişliği korur.
Direkler ve gol çizgisi arena yarıçapının %3'ü kadar içeri alınır; arena değişmez.
Direkler, file, gol algısı ve tema maskeleri aynı geometriyi kullanır. Boyut yeniden
başlatmada korunur. Dar kale açıklığı, çapı açıklıktan büyük logoları geçirmez.
Takım boyutu fizik yarıçapını da değiştirir. PNG/JPG logoların en-boy oranı ve
PNG şeffaflığı korunur; görsel fizik diskiyle aynı çapta dairesel maskeyle çizilir.
Logo çerçevesi veya logonun arkasında renkli dolgu yoktur. Ekrandaki geri düğmesi veya
Escape/Android geri tuşu önceki akışa döner; maçtan ayrılınca fizik saati durur.

Tema kimlikleri: `neon_purple`, `fire_arena`, `electric_blue`, `rainbow_neon`,
`emerald_arena`. Görsel tanımlar `services/arena_themes.py` içinde veri olarak
tutulur: koyu arka plan rengi, isteğe bağlı görsel yolu, çember paleti, glow,
atmosfer ve hareket/temas efektleri. Yeni tema eklemek için bu kayıt genişletilir.
Yeni ARKA PLAN galerisi `services/backgrounds.py` içindeki beş bağımsız kaydı kullanır:
Neon Stadium (`assets/background1.png`), Stadium Night (`assets/backgrounds/stadium_night.png`),
Rainy Stadium (`assets/backgrounds/stadium_rain.png`), Classic Football
(`assets/backgrounds/retro_pitch.png`) ve Cosmic Arena (`assets/backgrounds/cosmic_stadium.png`).
`assets/backgraund/` altındaki aynı isimli görseller de desteklenir. Eksik/bozuk
görseller önce Neon Stadium dosyasına, ardından `assets/backgraund1.png` veya
`assets/backgraund/backgraund1.png` dosyasına, o da yoksa koyu varsayılana döner.
Dosya isimleri değiştirilmez. `background_id` içermeyen eski maç ayarlarında önceki
temaya bağlı arka plan davranışı ve `background` yolu desteklenir.
Tema ve arka plan tercihleri Kivy `App.user_data_dir` içindeki `match_preferences.json`
dosyasında ayrı alanlarda saklanır; mevcut takım veri konumu ve takım JSON'u değiştirilmez.
BENİM ARKA PLANLARIM galerisi aynı dizindeki `custom_backgrounds.json` kayıtlarını kullanır:
her kayıtta UUID, görünen isim, göreli `path` ve UTC `added_at` tarihi bulunur.
PNG/JPG/JPEG dosyaları `custom_backgrounds/<UUID>.<uzantı>` olarak kopyalanır.
Aynı isimli görseller eklenebilir. Android `content://` belgeleri mevcut SAF servisiyle
önce okunabilir geçici kopyaya alınır; URI bir yerel dosya yolu gibi kullanılmaz.
Yeni görsel otomatik seçilir, son seçim ID ile korunur. Hazır karta dönmek kitaplığı silmez.
Her özel kartın SİL düğmesi onay ister; yalnızca UUID'li uygulama kopyası ve kaydı
silinir. Kullanıcının orijinal fotoğrafı ve hazır görseller silinmez. Seçili görsel
silinirse güvenli varsayılana dönülür; arena teması korunur. JSON atomik değiştirilir;
bozuk kayıt korunup UUID'li dosyalar kurtarılır, sonraki yazmada yedek JSON oluşturulur.
Eski `data/backgrounds/` kopyaları ve tercihler bir kez aktarılır; kaynaklar silinmez.
Silinen eski görseller sonraki açılışta yeniden aktarılmaz.
Arka plan merkezden kırpılarak, oranı bozulmadan ekranı doldurur. Önizlemeler en fazla
144×256 pikseldir; özel önizlemeler `custom_backgrounds/<UUID>.thumb.png` olarak diskte
saklanır. Sadece görünür özel kartlar texture tutar; önbellek 8 önizleme ve 2 tam boy
texture ile sınırlıdır. Render
sırasında dosya okunmaz. Çember ve efekt paleti yalnızca arena temasından gelir.
Çember ve dönen kale her zaman Canvas üzerinde ayrı çizilir. Tema verileri fizik
motoruna veya gol açıklığının geometrisine aktarılmaz.
Dekoratif renk akışı ve glow darbeleri ayrı render saatinden ilerler; kale
hızı bunları hızlandırmaz. İsteğe bağlı PNG/WebP atlas katmanları için
[efekt dosyası sözleşmesine](assets/effects/README.md) bakın. Fire Arena, Electric
Blue ve Rainbow Neon artık `assets/arena_effects/` altındaki kendi RGBA PNG
görsellerini kullanır. Şeffaf kenarlar kaynak-piksel kalibrasyonuyla hesaba katılır;
parlak halka fiziksel çembere oturur. Kale açıklığı Mesh'in boş açısal dilimiyle
oluşturulur, arka plan kapatılmaz. Tek PNG gerçek kare kare animasyon sağlamaz;
yalnızca hafif parlaklık değişimi, dönüş ve sınırlı parçacıklar uygulanır.
Fire Arena'nın halka dönüşü 18 saniye/tur, Electric Blue'nun dönüşü 12 saniye/tur
olarak ayarlanmıştır. Rainbow Neon'un mevcut 6°/s dönüşü korunur. Konumu rastgele
seçilen yerel elektrik parlamaları 0,16 saniye yaşar; az sayıda mavi parçacıkla
desteklenir. Tüm görsel zamanlar Kivy Clock'un render süresinden ilerler.
Maç bitince halka dönüşü donar, kısa efektler söner; duyuru kuyruğu bittiğinde ve
yeniden başlat düğmesi hazır olduğunda maç ekranının Clock olayı kapatılır.
Yeniden başlatma olayı tekrar açar; bağımsız gol müziği fade-out saatleri etkilenmez.

Fire Arena ayrıca `screens/fire_particles.py` içinde 60 alev dili ve 12 küçük
kıvılcımdan oluşan sabit bir havuz kullanır. Aynı parçacık nesneleri tekrar
kullanılır; her yuvanın ayrı rastgelelik üreteci, doğum zamanı, ömrü, hızı,
boyutu ve parlaklığı vardır. Mutlak render zamanı konumu, dışa/yukarı sürüklenmeyi,
bükülmeyi, büyümeyi ve alfa/renk geçişini belirler; bütün alevler aynı anda
yenilenmez. PNG ana halka olarak korunur. Yeni katman tek vertex-renkli Mesh
grubudur; ek Widget veya parçacık başına Canvas talimatı oluşturulmaz.
Kale açıklığına taşan üçgenler, güncel iki kenar yarı düzlemine göre kırpılır.
Bu maske yalnızca çizimi etkiler; fizik ve motorun rastgelelik üreteci değişmez.
Maç sonunda yeni alev doğmaz, kalanlar en fazla 1,15 saniyede söner. Diğer
temalara bu yeni katman eklenmez. `python -m pytest tests/test_fire_particles.py -q`
ömrü, nesne tekrar kullanımını, 30/60/120 FPS eşitliğini ve GPU açıklık maskesini sınar.

Electric Blue ayrıca `screens/electric_effects.py` içinde 6 yıldırım ve 24 enerji
parçacığı için yeniden kullanılan havuzlar kullanır. 0,15–0,4 saniyelik yıldırımlar
5–9 ana parçadan ve isteğe bağlı kısa yan dallardan oluşur. Çapraz kollar yarıçapın
%8–18'i kadar dışa uzanır; 15–45 derecelik dalgalar iki yönde çember boyunca ilerler.
Önceki kalınlığın 2,5 katındaki çizgiler mavi dış glow, cyan gövde ve beyaz çekirdek
olarak PNG'nin üstünde, kale ve logoların altında tek vertex-renkli Mesh ile çizilir.
Fire'ın kırpma yardımcıları güncel kale açıklığını glow dahil tamamen boş bırakır.
PNG dönüşü korunur; kısa parlaklık artışı yalnızca elektrik katmanını etkiler.
Maç sonunda üretim durur ve kalan efektler söner; tema ekranı kapanınca Mesh temizlenir.
`python -m pytest tests/test_electric_effects.py -q` bu davranışları sınar.

Windows penceresi 450×800 açılır. Simülasyon koordinatlarında merkez (0, 0),
yukarı yön +Y ve arena yarıçapı 400 birimdir. Ekran boyutu yalnızca çizim ölçeğini
değiştirir. Arena çapı portre ekran genişliğinin yaklaşık %74'üdür. Clock render
güncellemelerini sağlar; biriktirilen süre 1/120 saniyelik
fizik adımlarıyla tüketilir. Çok uzun bir render duraklaması da zamanı atlamaz.

Başlangıç ve gol sonrası hız 880–1200 birim/s, hız sınırları 680–1360 birim/s'dir.
Her sabit fizik adımı, göreli disk/direk hareketine göre ek çarpışma alt adımlarına
bölünür. Render tarafında çok renkli neon arena, hafif glow, kısa hareket izleri,
temas kıvılcımları ve duvar parlamaları sabit Canvas havuzlarıyla çizilir. Efektler
fizik durumunu ve motorun rastgelelik üretecini değiştirmez. Skor alanında gerçek
logolar, kısaltılan uzun takım adları, büyük beyaz skor ve futbol dakikası bulunur.
Üst logolar önceki sürüme göre 1,7 kat büyüktür; arena içindeki boyutlar değişmez.

Ses dosyaları `assets/sounds/` altında kendi adlarıyla kullanılır. Efektler uygulama
açılışında, takımların özel gol müzikleri maç başlamadan yüklenir. `services/audio.py`
her efekt için 2–3 ayrı Sound nesnesi ve her takım müziği için iki bağımsız ses
yuvası kullanır; çarpışmada diskten yeniden yükleme yapılmaz. Aynı temasın tekrar
bildirilmesi motor tarafında engellenir, çarpışma seslerinde ayrıca 100 ms cooldown
uygulanır. Hafif disk temasları `soft_puck.wav`, sert temaslar `flick.wav` kullanır.
Takım müziği ve `goal.mp3` eşzamanlı çalar; her müzik yuvasının 5 saniyelik bağımsız
zamanlayıcısı vardır. Dosya daha kısaysa doğal olarak önce biter. Bir takımı durdurmak
diğer takımın müziğini etkilemez. Üçüncü ardışık takım müziği aynı takımın dolu
havuzundan bir yuvayı kullanır; diğer takımın kanallarını kesmez.

Varsayılan efekt seviyesi %32, özel müzik seviyesi %28'dir. `set_effects_volume()`
gelecekteki genel ses ayarına bağlanabilir. Sarı/kırmızı kart sesleri hazır olay
eşlemelerine sahiptir (`yellow_card`/`red_card`). Kart sesleri, sıradaki kart
animasyonu görünür olduğunda çalınır. SDL2 kullanılırsa eşzamanlı efekt ve takım
müzikleri için en az 32 mixer kanalı ayrılır; ses havuzları yine sınırlıdır.
Maçtan ayrılma ve yeniden başlatma müzikleri/zamanlayıcıları temizler. Uygulama
arka plana alınırken sesler durur; dönüşte durmuş takım müzikleri otomatik başlamaz.

Eşit kütleli diskler normal yönde elastik momentum aktarır. Hız sınırları
çarpışma çözümünden sonra uygulanır; bu sınırlama devreye girerse toplam kinetik
enerji korunmayabilir. Dönen direklerin yüzey hızları çarpışmaya katılır.
Kale çizgisi iki direği birleştiren kiriştir; diskin tamamı çizginin dışına
geçtiğinde, açıklığa sığıyorsa ve direk teması yoksa gol yazılır. Her gol sonrası
yalnızca gol atan disk merkezde yeniden doğar. Merkez rakip tarafından
kaplanmışsa, rakibin konum/hızını değiştirmeden en yakın güvenli noktaya taşınır.
Diğer disk normal fizik akışına devam eder. Bu aynı zamanda mükerrer golü engeller.

Her maçta ayrı bir rastgelelik üreteciyle 0–5 sarı kart ve %8 olasılıkla en fazla
bir kırmızı kart planlanır. Takımlar rastgele seçilir; dakikalar maç boyunca
aralıklı slotlara dağıtılır. `engine/cards.py` yalnızca görsel/istatistik olayları
üretir. Kartlar disklerin hızını, yönünü, kütlesini veya çarpışmalarını değiştirmez.
Kart geçmişi maç boyunca bellekte tutulur; yeniden başlatmada temizlenir.

GOOL duyurusu çember ve skor alanı arasındadır; büyüme, altın renkli parlama ve
yumuşak kaybolmayla 1,8 saniye sürer. Kart duyurusu arena altında takım adı ve
kart rengiyle 1,5 saniye görünür. Yakın gol/kart duyuruları sıraya alınır; saat
ve fizik çalışmaya devam eder. Maç bitince kuyruk tamamlanır ve sonuç paneli
gösterilir. Başlıktaki küçük kart sayaçları takım logolarının dış yanında yer alır.

3 saniyelik geri sayımın ardından 55 saniye maç oynanır. Futbol dakikası 1–90
arasında ilerler. Final paneli görünür kalır ve 3 saniye sonra yeniden başlatma
düğmesi etkinleşir. Gol geçmişi yalnızca bellekte tutulur.
Final panelinde ev sahibi solda, deplasman sağdadır. Her sütunda gerçek logo ve
tam takım adı, ortak büyük final skorunun altında yalnızca o takımın kronolojik
gol dakikaları bulunur. Uzun isimler ve gol listeleri ayrı ayrı kaydırılabilir;
gol atamayan sütunda “Gol atılmadı” gösterilir. Liste her render karesinde yeniden
kurulmaz; sonuç değişmedikçe kullanıcının kaydırma konumu korunur.
Kart dakikaları aynı takım sütununda sarı/kırmızı küçük simgelerle gösterilir.
Kartı olmayan takım için boş kart bölümü ayrılmaz.
Sonuç kartları font/emoji karakterleri yerine Canvas `RoundedRectangle` kullanır;
yanlarında `24' SARI` ve `77' KIRMIZI` gibi normal metin bulunur. Kart satırları
gol listesiyle aynı kaydırılabilir içerikte tutulur.

Görsel smoke kontrolü: `python tools/smoke_ui.py`. Kullanıcı takımlarını
değiştirmeden `.smoke_runtime/` altında örnek takım ve ekran görüntüleri üretir;
menü, takım ekranı, kurulum, maç, final, yeniden başlatma ve geri dönüşü çalıştırır.
`python tools/smoke_events.py` ise kullanıcı kayıtlarına dokunmadan GOOL, kart
kuyruğu, kart sayaçları ve sonuç panelini 320×640, 450×800, 720×1280 boyutlarında
görüntüler; çıktıları `.smoke_runtime/events_*.png` dosyalarına kaydeder.

Gerçek ses kontrolü: `python tools/smoke_audio.py`. Düşük ses seviyesinde 11
dosyanın yüklenmesini, bağımsız müzik durdurmayı ve 5 saniye sınırını sınar. Windows'ta
en az dört gerçek SDL2 mixer kanalının aynı anda çalıştığını kontrol eder. Bu test
fiziksel hoparlör çıkışının veya ses kalitesinin dinleme testi değildir.

APK ve video kaydı bu aşamanın kapsamı dışındadır.
Android dosya seçicisi, depolama yaşam döngüsü, geri tuşu ve portre kilidi gerçek
cihazda test edilmemiştir. Android paketleme henüz yapılmamıştır.
Android WAV/MP3 çözücüleri, eşzamanlı kanallar ve duraklatma/dönüş yaşam döngüsü
gerçek cihazda doğrulanmamıştır; uygun Kivy ses sağlayıcısının paketlenmesi gerekir.
