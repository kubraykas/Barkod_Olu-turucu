# Barkod Oluşturucu

Fotoğraftaki etikete benzer (gri etiket + yoğun QR kod + yanında parça no / lot metni) çok sayıda örnek barkod/QR etiket üreten Python betiği. Her örnek farklı boyutta ve farklı bozunma seviyesinde (normal, hafif tozlu, tozlu, yarı silik, silik, çizik, leke, bulanık, parlama, kısmen kapalı, açılı çekim, karışık) üretilir; ayrıca okunabilirlik testi ile raporlanır.

## Kurulum

```bash
pip install pillow numpy qrcode opencv-python
```

## Kullanım

```bash
python "barkod_uretici (1).py"
python "barkod_uretici (1).py" --adet 120 --boyut 10,14,20,30 --dpi 600
python "barkod_uretici (1).py" --tur normal,yari_silik,toz --adet 30
```

### Parametreler

| Parametre | Varsayılan | Açıklama |
|---|---|---|
| `--adet` | 60 | Üretilecek örnek sayısı |
| `--cikti` | `barkod_ciktilari` | Çıktı klasörü |
| `--dpi` | 600 | Çözünürlük (baskı için 600 önerilir) |
| `--boyut` | `10,14,18,24,30` | QR kod kenar uzunlukları (mm), virgülle |
| `--tur` | `normal,yari_silik,silik,bulanik` | Bozunma türleri, virgülle (`hepsi` ile tüm seçenekler) |
| `--duzen` | `hepsi` | Metnin QR'a göre konumu: `sag`, `sol`, `ust`, `alt` |
| `--duzeltme` | `M` | QR hata düzeltme seviyesi (`L`, `M`, `Q`, `H`) |
| `--yuk-uzunluk` | 70 | QR içindeki metin uzunluğu (kod yoğunluğunu belirler) |
| `--siddet` | rastgele | 0-1 arası sabit bozunma şiddeti |
| `--seed` | 42 | Aynı sayıyla aynı örnekler tekrar üretilir |
| `--sayfa-yok` | kapalı | A4 baskı sayfalarını üretmez |
| `--tum-pdf` | kapalı | Klasördeki tüm etiketleri tek PDF seti olarak basar |

## Çıktılar

Varsayılan olarak `./barkod_ciktilari` klasörüne yazılır:

- `etiketler/` — her örnek için ayrı PNG (gerçek boyutta, DPI bilgisi gömülü)
- `baskilar/` — A4 baskı sayfaları (PNG) + `baski_sayfalari.pdf`
- `tum_pdf/` — `--tum-pdf` ile üretilen birleşik PDF seti
- `ornekler.csv` — her örneğin türü, şiddeti, boyutu, içeriği ve okunabilirlik sonucu
- `ozet.csv` — tür bazında okuma oranı (piksel/modül seviyelerine göre)

## Baskı Notu

`baski_sayfalari.pdf` dosyasını **%100 / "Gerçek boyut"** ile yazdırın ("Sığdır" seçeneği kapalı olmalı). Sayfadaki 50 mm cetvel çubuğunu ölçerek ölçeğin doğru olduğunu kontrol edin.

> Etiketlerdeki parça no, lot ve seri numaraları rastgele üretilmiştir; gerçek üretim verisi değildir.
