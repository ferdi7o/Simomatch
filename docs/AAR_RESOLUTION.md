# capture_manifest AAR çözümleme düzeltmesi

## Kök neden ve kaynak incelemesi

python-for-android develop `build.py`, `--add-aar` dosyasını **üretilen Gradle
proje kökünün `libs/` dizinine** kopyalar. Bu dizin kaynak projenin `android_src/`
dizini veya JAR'lar için kullanılan `src/main/libs/` dizini değildir.

`build.tmpl.gradle` şu bağımlılığı üretir:

```groovy
implementation(name: 'capture_manifest', ext: 'aar')
```

Güncel şablonun repository listesinde google()/mavenCentral() vardır; yerel
`libs/` araması varsayılan olarak yoktur. Dosyanın kaynak klasörde hatta
Gradle `libs/` içinde bulunması, bir **isimle tanımlanan** bağımlılığın çözülmesi
için yeterli değildir. Kullanıcının WSL çıktısında doğruladığı eksik `flatDir`,
`Could not find :capture_manifest:.` hatasını açıklıyor.

Önceki entegrasyonda eksik kalan repository satırı kalıcı spec'e eklendi:

```ini
android.add_src = android_src
android.add_aars = android_src/capture_manifest.aar
android.add_gradle_repositories = flatDir { dirs 'libs' }
```

Son satırı **dış çift tırnak olmadan** yazın. `libs` için iç tek tırnaklar
Groovy ifadesinin parçasıdır. Güncel Buildozer SpecParser CSV liste değerlerini
literal olarak p4a `--add-gradle-repository` argümanına geçirir; fazladan dış
tırnaklar repository bloğunu Groovy string ifadesine dönüştürebilir.

Buildozer bu ayarı her paketlemede p4a'ya iletir; p4a şablonu ifadeyi
`allprojects.repositories` içine yazar. `.buildozer` içindeki build.gradle
elle değiştirilmez. Temiz derleme veya cache silme yapılmadı/gerekmiyor.

## AAR ve servis durumu

Mevcut arşivde CRC hatası bulunmadı. `AndroidManifest.xml`, geçerli (bilerek
boş) `classes.jar` ve `R.txt` bulunuyor. Servis adı, `exported=false` ve
`foregroundServiceType=mediaProjection` korunuyor. Boş classes.jar hata değildir:
bu arşiv yalnızca manifest bildirimi sağlar; gerçek CaptureService.java
`android.add_src` ile derlenir. AAR veya Java kaynağı yeniden üretilmedi/değiştirilmedi.

Kayıt izinleri değişmedi. `p4a.branch`, API/NDK, Python requirements ve uygulama
verileri değiştirilmedi. Araçtaki yeni repository-only düzeltmesi yalnızca
`android.add_gradle_repositories` anahtarını günceller; mevcut repository'leri korur.

AAR'sız seçenek olarak develop'un `--extra-manifest-application-xml` desteği
değerlendirildi. Bunun için Buildozer/p4a ek argüman aktarımı ve XML escaping
akışı değiştirilmeliydi. Gerek kalmadı: mevcut servis manifestini ve Java yolunu
koruyan desteklenen tek repository ayarı daha küçük bir düzeltme.

## Gerçek WSL projesinde uygulanacak adımlar

`buildozer.spec` rsync dışında bırakılıyorsa Windows satırı otomatik aktarılmaz.
Yeni araç dosyasını da WSL'ye kopyalayın ve **gerçek derleme klasöründe** çalıştırın:

```bash
python3 tools/check_android_capture.py --fix-aar-repository --spec buildozer.spec
buildozer -v android debug
```

İlk komut spec'in yedeğini alır ve yalnız repository ayarını değiştirir. Bu hata
için genel `--apply` seçeneğine ihtiyaç yoktur. Diğer Maven repository'leriniz
varsa korunarak `flatDir` eklenir. Manuel birleştirmede de mevcut
`android.add_gradle_repositories` satırını ezmeyin; virgülle yeni ifadeyi ekleyin.

Gerçek üretilmiş Gradle proje klasörü biliniyorsa kontrol edin:

```bash
python3 tools/check_android_capture.py --gradle-project /GERCEK/P4A/DIST/KLASORU
```

Bu kontrol AAR'ın `libs/` içindeki kopyasını, kaynakla eşleşmesini, named
dependency ve repository bloklarını salt okunur olarak denetler. Derlemenin
başarısını veya dependency çözümleyicisini çalıştırmış sayılmaz. Eski üretilmiş
build.gradle hâlâ repository içermiyorsa güncel spec ile paketlemeyi tekrar
çalıştırın; üretilmiş dosyaya elle eklemeyin.

## APK / DEX doğrulaması

### Art arda iki gerçek derleme

Gerçek WSL derleme ortamınızı etkinleştirin. Proje dosyalarını aktarırken yeni
`tools/verify_two_android_builds.py` ve güncel `tools/check_android_capture.py`
dosyalarını da aktarın. Aşağıdaki yolları kendi dist ve **güncel** APK adınızla
değiştirin:

```bash
python3 tools/check_android_capture.py --fix-aar-repository --spec buildozer.spec
python3 tools/verify_two_android_builds.py \
  --gradle-project .buildozer/android/platform/build-arm64-v8a/dists/simomatch \
  --apk bin/YENI_APK_DOSYASI.apk
```

İkinci komut `buildozer -v android debug` komutunu **iki kez sırayla** çalıştırır.
Her derlemeden sonra şunları denetler:

1. Spec değişmedi; API/NDK/p4a dalı/requirements korunuyor.
2. build.gradle gerçekten yeniden yazılmış; eski dosyaya bakılarak başarı verilmiyor.
3. Yeniden üretilmiş Gradle'da libs/flatDir, AAR kopyası ve bağımlılık doğru.
4. APK'nin DEX class_defs tablosunda CaptureService tanımı var (mevcut check_android_capture denetimi).
5. Seçilen bin/APK dosyasının SHA-256'sı bu Gradle projesinin debug APK çıktısıyla aynı.

Yalnız iki tur da geçerse `TWO_BUILDS_VERIFIED` yazar.
`bin/capture-two-builds.json` her turun Gradle/APK hash'lerini ve DEX sonucunu
tutar. İlk tur geçip ikinci bozulursa rapor `complete:false` kalır; başarısız
derlemeden sonra devam edip eski APK'yi başarı saymaz. Hiçbir clean/silme işlemi,
üretilmiş Gradle'a yama veya spec yeniden yazımı yapmaz. Zaman damgası değişmezse
"yeniden üretildi" iddiası yerine hata verir.

Windows testlerinde bu orkestrasyon **simüle edilmiş** builder ile sınanır;
bu, WSL'de iki Android derlemesi yapıldığı anlamına gelmez. Gerçek iki derleme
doğrulaması için bu komutun sizin WSL ortamınızda başarıyla tamamlanması gerekir.
Bu eklemeden sonraki tam Windows test koşusu: **545 test geçti** (115,45 saniye).

Bu eklemede değişen dosyalar: `tools/verify_two_android_builds.py`,
`tests/test_two_android_builds.py`, `docs/AAR_RESOLUTION.md`. Mevcut kalıcı
`android.add_gradle_repositories` ayarı doğru olduğundan tekrar değiştirilmedi.

Derleme başarılı olduktan sonra yeni APK'nin **gerçek dosya adını** kullanın:

```bash
python3 tools/check_android_capture.py --apk bin/YENI_APK_DOSYASI.apk
```

Beklenen çıktı: `CAPTURE_CLASS_DEFINED_IN_DEX classes....dex`.
Bu, string araması değil DEX class_defs tablosu kontrolüdür. Manifest ve cihaz
yüklemesi için SDK `apkanalyzer manifest print ...` ve cihazdaki
`CAPTURE_SERVICE_CLASS_LOADED` logunu da kontrol edin. Windows kaynak kontrolü
APK/DEX veya Android foreground service çalışmasını doğrulamaz.

## Değişen dosyalar

- `buildozer.spec`: repository satırı.
- `tools/check_android_capture.py`: repository-only WSL düzeltmesi, AAR doğrulama ve üretilmiş Gradle salt okunur kontrolü.
- `tests/test_android_capture_packaging.py`: eksik repository, geçerli arşiv, WSL ayarlarını koruma testleri.
- `docs/ANDROID_VIDEO.md`, `docs/TWO_ANDROID_ISSUES.md`: gerekli repository satırı belgelendi.
- `docs/AAR_RESOLUTION.md`: bu rapor.

Bu ortamda WSL erişimi/Android SDK ve gerçek APK bulunmadığından Android derlemesi
ve nihai APK sınıfı burada doğrulanamadı. Bu kısıt başarı mesajıyla gizlenmez.

Windows Python 3.10.9 / Kivy 2.3.1 tam test koşusu: **538 test geçti**
(103,09 saniye). AAR ZIP/CRC ve iç JAR doğrulaması başarılı. Mevcut
`CaptureService.java` kaynağı ve foreground service manifesti değişmedi.

## Kaynaklar

- https://github.com/kivy/python-for-android/blob/develop/pythonforandroid/bootstraps/common/build/build.py
- https://github.com/kivy/python-for-android/blob/develop/pythonforandroid/bootstraps/common/build/templates/build.tmpl.gradle
- https://github.com/kivy/buildozer/blob/master/buildozer/targets/android.py
- https://docs.gradle.org/current/userguide/supported_repository_types.html#sub:flat_dir_resolver
