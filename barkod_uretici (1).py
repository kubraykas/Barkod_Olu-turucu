#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Avitaş barkod okunabilirlik testi - örnek barkod üretici
=========================================================

Fotoğraftaki etikete benzer (gri etiket + yoğun QR kod + yanında parça no / lot metni)
çok sayıda örnek üretir. Her örnek farklı boyutta ve farklı bozunmada olur:
normal, hafif tozlu, tozlu, yarı silik, silik, çizik, leke, bulanık, parlama,
kısmen kapalı, açılı çekim ve karışık.

Kurulum (bir kez):
    pip install pillow numpy qrcode opencv-python

Çalıştırma (VS Code'da sağ üstteki ▶ ya da terminalde):
    python barkod_uretici.py
    python barkod_uretici.py --adet 120 --boyut 10,14,20,30 --dpi 600
    python barkod_uretici.py --tur normal,yari_silik,toz --adet 30

Çıktılar (varsayılan: ./barkod_ciktilari):
    etiketler/        her örnek için ayrı PNG (gerçek boyutta, dpi bilgisi gömülü)
    baskilar/         A4 baskı sayfaları (PNG) + baski_sayfalari.pdf
    ornekler.csv      her örneğin türü, şiddeti, boyutu, içeriği ve okunabilirlik sonucu
    ozet.csv          tür bazında okuma oranı (piksel/modül seviyelerine göre)

Baskı: baski_sayfalari.pdf dosyasını %100 / "Gerçek boyut" ile yazdırın ("Sığdır" kapalı).
Sayfadaki 50 mm cetvel çubuğunu ölçerek ölçeğin doğru olduğunu kontrol edin.

Not: Etiketlerdeki parça no, lot ve seri numaraları rastgele üretilmiştir; gerçek Avitaş
verisi değildir.
"""

import argparse
import csv
import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q
except ImportError:  # pragma: no cover
    sys.exit("Eksik paket: pip install qrcode pillow numpy opencv-python")

try:
    import cv2  # okunabilirlik testi için (isteğe bağlı)
    CV2_VAR = True
except ImportError:  # pragma: no cover
    CV2_VAR = False

DUZELTME = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M, "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H}
PPM_LISTESI = (2, 3, 4, 6, 8)  # kamera simülasyonunda denenecek piksel/modül değerleri
DUZEN_LISTESI = ("sag", "sol", "ust", "alt")  # metnin QR'a göre konumu: sağda/solda (dikey) ya da üstte/altta (yatay)

# --------------------------------------------------------------------------------------
# Yardımcılar
# --------------------------------------------------------------------------------------


def mm_px(mm, dpi):
    return mm * dpi / 25.4


def yazi_tipi(boyut_px):
    adaylar = ["tahoma.ttf", "arial.ttf", "DejaVuSans.ttf", "Arial.ttf",
               "C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/arial.ttf",
               "/Library/Fonts/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for a in adaylar:
        try:
            return ImageFont.truetype(a, max(6, int(boyut_px)))
        except OSError:
            continue
    return ImageFont.load_default()


def dusuk_frekans(nrng, h, w, olcek):
    """0-1 arası, yumuşak (düşük frekanslı) rastgele alan üretir."""
    kh, kw = max(2, int(h // olcek)), max(2, int(w // olcek))
    k = nrng.random((kh, kw)).astype(np.float32)
    im = Image.fromarray((k * 255).astype("uint8")).resize((w, h), Image.BICUBIC)
    a = np.asarray(im, dtype=np.float32) / 255.0
    return (a - a.min()) / (a.max() - a.min() + 1e-6)


def pil(arr):
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8"), "RGB")


def dizi(img):
    return np.asarray(img.convert("RGB"), dtype=np.float32)


# --------------------------------------------------------------------------------------
# İçerik ve temiz etiket
# --------------------------------------------------------------------------------------


def rastgele_icerik(rng, uzunluk):
    parca = f"A 961 {rng.randint(100, 999)} {rng.randint(10, 99)} {rng.randint(0, 99):02d}"
    lot = f"{rng.choice([2022, 2023, 2024, 2025, 2026])}-{rng.randint(10000, 99999)}"
    yuk = f"{parca};{lot};AVITAS;HAT-{rng.randint(1, 8)};V{rng.randint(1, 3)};SN{rng.randint(0, 999999):06d}"
    while len(yuk) < uzunluk:
        yuk += f";{rng.randint(0, 9999999):07d}"
    return parca, lot, yuk


def qr_matrisi(yuk, duzeltme):
    qr = qrcode.QRCode(version=None, error_correction=DUZELTME[duzeltme], box_size=1, border=0)
    qr.add_data(yuk)
    qr.make(fit=True)
    return np.array(qr.get_matrix(), dtype=bool)


def temiz_etiket(rng, nrng, dpi, qr_mm, matris, parca, lot, duzen="sag"):
    """Gri etiket + QR + iki satır metin. Metin konumu 'duzen' ile değişir:
    sag/sol = QR'ın yanında dikey (90° döndürülmüş) şerit; ust/alt = QR'ın üstünde/altında yatay iki satır.
    (görüntü, bağlam) döner."""
    n = matris.shape[0]
    qr_px = max(n * 3, int(round(mm_px(qr_mm, dpi))))
    mod_px = qr_px / n
    pad = int(max(mm_px(1.2, dpi), 2 * mod_px))

    fs = qr_px * 0.10
    font = yazi_tipi(fs)
    en_uzun = max(font.getlength(parca), font.getlength(lot))
    if en_uzun > qr_px * 0.95:
        fs = fs * qr_px * 0.95 / en_uzun
        font = yazi_tipi(fs)
    satir_h = int(fs * 1.3)

    # hangi bilginin önce (üstte/solda) geleceği örnekten örneğe değişsin
    satirlar = [parca, lot]
    if rng.random() < 0.5:
        satirlar = satirlar[::-1]

    zemin_g = rng.randint(190, 225)
    zemin = np.array([zemin_g, zemin_g, zemin_g - rng.randint(0, 6)], dtype=np.float32)
    murekkep_g = rng.randint(30, 65)
    murekkep = np.array([murekkep_g] * 3, dtype=np.float32)

    if duzen in ("sag", "sol"):
        serit_w = satir_h * 2 + pad
        w = pad + qr_px + pad + serit_w
        h = qr_px + 2 * pad
        qr_y0 = pad
        if duzen == "sag":
            qr_x0, serit_x0 = pad, pad + qr_px + pad
        else:
            serit_x0, qr_x0 = pad, pad + serit_w + pad
    else:  # "ust" / "alt"
        metin_h = satir_h * 2 + int(satir_h * 0.35)
        w = qr_px + 2 * pad
        h = qr_px + 2 * pad + metin_h
        qr_x0 = pad
        if duzen == "ust":
            metin_y0, qr_y0 = pad, pad + metin_h
        else:
            qr_y0, metin_y0 = pad, pad + qr_px + pad

    arr = np.ones((h, w, 3), dtype=np.float32) * zemin
    # hafif ışık gradyanı (gerçek etiket yüzeyi gibi)
    arr *= (0.94 + 0.06 * dusuk_frekans(nrng, h, w, max(20, h // 2)))[..., None]

    kod = Image.fromarray((matris * 255).astype("uint8")).resize((qr_px, qr_px), Image.NEAREST)
    kod = np.asarray(kod) > 127
    bolge = arr[qr_y0:qr_y0 + qr_px, qr_x0:qr_x0 + qr_px]
    bolge[kod] = murekkep

    im = pil(arr)
    if duzen in ("sag", "sol"):
        for k, metin in enumerate(satirlar):
            tmp = Image.new("L", (int(font.getlength(metin)) + 4, satir_h), 0)
            ImageDraw.Draw(tmp).text((2, 0), metin, font=font, fill=255)
            tmp = tmp.rotate(90, expand=True)
            x = serit_x0 + k * satir_h
            y = qr_y0 + (qr_px - tmp.size[1]) // 2
            im.paste(Image.new("RGB", tmp.size, tuple(int(v) for v in murekkep)), (x, y), tmp)
    else:
        d = ImageDraw.Draw(im)
        for k, metin in enumerate(satirlar):
            x = (w - font.getlength(metin)) / 2
            y = metin_y0 + k * satir_h
            d.text((x, y), metin, font=font, fill=tuple(int(v) for v in murekkep))

    ctx = dict(rng=rng, nrng=nrng, zemin=zemin, mod_px=mod_px,
               kutu=(qr_x0, qr_y0, qr_x0 + qr_px, qr_y0 + qr_px), w=w, h=h, dpi=dpi)
    return dizi(im), ctx


# --------------------------------------------------------------------------------------
# Bozunma fonksiyonları: f(arr, ctx, s) -> arr   (s: 0-1 şiddet)
# --------------------------------------------------------------------------------------


def _kaplama(arr, cizim):
    """cizim(draw) ile RGBA katman çiz, arr üzerine bindir."""
    h, w = arr.shape[:2]
    kat = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cizim(ImageDraw.Draw(kat))
    return dizi(Image.alpha_composite(pil(arr).convert("RGBA"), kat).convert("RGB"))


def bz_sil(arr, c, s):
    """Tüm etiketin solması: kontrast düşer."""
    a = 0.35 + 0.6 * s
    return c["zemin"] + (arr - c["zemin"]) * (1 - a)


def bz_yari_silik(arr, c, s):
    """Etiketin bir yarısı silik, diğer yarısı görünür."""
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    aci = c["rng"].uniform(0, 2 * math.pi)
    t = (xx / w - 0.5) * math.cos(aci) + (yy / h - 0.5) * math.sin(aci)
    t = (t - t.min()) / (t.max() - t.min() + 1e-6)
    t += (dusuk_frekans(c["nrng"], h, w, c["mod_px"] * 6) - 0.5) * 0.25
    m = np.clip((t - 0.40) / 0.25, 0, 1)
    a = m * (0.55 + 0.4 * s)
    return c["zemin"] + (arr - c["zemin"]) * (1 - a[..., None])


def bz_toz(arr, c, s):
    """Toz tabakası + ince toz lekeleri."""
    h, w = arr.shape[:2]
    duman = dusuk_frekans(c["nrng"], h, w, max(8, c["mod_px"] * 3))
    a = (0.08 + 0.32 * s) * duman
    toz_renk = np.array([172, 166, 156], dtype=np.float32)
    arr = arr * (1 - a[..., None]) + toz_renk * a[..., None]
    adet = int(h * w / (c["mod_px"] ** 2) * 0.12 * (0.3 + s))
    rng = c["rng"]

    def ciz(d):
        for _ in range(adet):
            r = rng.uniform(0.12, 0.55) * c["mod_px"]
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            g = rng.randint(110, 205)
            d.ellipse((x - r, y - r, x + r, y + r), fill=(g, g, g - 5, rng.randint(70, 190)))
    return _kaplama(arr, ciz)


def bz_cizik(arr, c, s):
    h, w = arr.shape[:2]
    rng = c["rng"]
    adet = int(2 + 9 * s)

    def ciz(d):
        for _ in range(adet):
            x0, y0 = rng.uniform(0, w), rng.uniform(0, h)
            aci = rng.uniform(0, math.pi)
            uz = rng.uniform(0.3, 1.0) * max(w, h)
            x1, y1 = x0 + uz * math.cos(aci), y0 + uz * math.sin(aci)
            acik = rng.random() < 0.65
            g = rng.randint(225, 250) if acik else rng.randint(60, 110)
            d.line((x0, y0, x1, y1), fill=(g, g, g, rng.randint(140, 235)),
                   width=max(1, int(c["mod_px"] * rng.uniform(0.08, 0.3))))
    return _kaplama(arr, ciz)


def bz_leke(arr, c, s):
    """Yağ/kir lekeleri."""
    h, w = arr.shape[:2]
    f = dusuk_frekans(c["nrng"], h, w, max(c["kutu"][2] // 3, 10))
    esik = 1 - (0.14 + 0.24 * s)
    m = np.clip((f - esik) / 0.07, 0, 1) * 0.7
    kir = np.array([96, 86, 74], dtype=np.float32)
    return arr * (1 - m[..., None]) + kir * m[..., None]


def bz_bulanik(arr, c, s):
    r = c["mod_px"] * (0.05 + 0.45 * s)
    return dizi(pil(arr).filter(ImageFilter.GaussianBlur(r)))


def bz_parlama(arr, c, s):
    """Yüzeyden yansıyan ışık: bölgesel kontrast kaybı."""
    h, w = arr.shape[:2]
    rng = c["rng"]
    cx, cy = rng.uniform(0.2, 0.8) * w, rng.uniform(0.2, 0.8) * h
    r = rng.uniform(0.35, 0.8) * max(w, h)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    g = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (r ** 2)))
    a = np.clip((0.5 + 0.45 * s) * g * 1.2, 0, 0.97)
    return arr * (1 - a[..., None]) + 255.0 * a[..., None]


def bz_kismi_kapali(arr, c, s):
    """Kir/bant gibi kodun bir kısmını örten yamalar (hata düzeltmeyi zorlar)."""
    rng, nrng = c["rng"], c["nrng"]
    x0, y0, x1, y1 = c["kutu"]
    kenar = x1 - x0
    adet = 1 + int(2 * s)
    out = arr.copy()
    for _ in range(adet):
        yw = kenar * rng.uniform(0.08, 0.20) * (0.6 + s)
        yh = kenar * rng.uniform(0.08, 0.20) * (0.6 + s)
        px, py = rng.uniform(x0, x1 - yw), rng.uniform(y0, y1 - yh)
        a, b, cc, d = int(px), int(py), int(px + yw), int(py + yh)
        yama = c["zemin"] * rng.uniform(0.82, 0.97)
        gur = nrng.normal(0, 6, (d - b, cc - a, 1)).astype(np.float32)
        out[b:d, a:cc] = yama + gur
    return out


def bz_acili(arr, c, s):
    """Eğik/açılı çekim: hafif dönme + yamulma."""
    h, w = arr.shape[:2]
    rng = c["rng"]
    k = s * 0.16 * min(w, h)
    q = [(rng.uniform(0, k), rng.uniform(0, k)),
         (rng.uniform(0, k), h - rng.uniform(0, k)),
         (w - rng.uniform(0, k), h - rng.uniform(0, k)),
         (w - rng.uniform(0, k), rng.uniform(0, k))]
    im = pil(arr).transform((w, h), Image.QUAD, [v for p in q for v in p], Image.BICUBIC)
    aci = rng.uniform(-1, 1) * s * 8
    im = im.rotate(aci, resample=Image.BICUBIC, expand=False, fillcolor=tuple(int(v) for v in c["zemin"]))
    return dizi(im)


def bz_capraz(arr, c, s):
    """Belirgin çapraz/diyagonal duruş: acili'den daha güçlü döndürme (20-75°) + perspektif yamulma."""
    h, w = arr.shape[:2]
    rng = c["rng"]
    k = (0.05 + 0.10 * s) * min(w, h)
    q = [(rng.uniform(0, k), rng.uniform(0, k)),
         (rng.uniform(0, k), h - rng.uniform(0, k)),
         (w - rng.uniform(0, k), h - rng.uniform(0, k)),
         (w - rng.uniform(0, k), rng.uniform(0, k))]
    im = pil(arr).transform((w, h), Image.QUAD, [v for p in q for v in p], Image.BICUBIC)
    aci = rng.choice((-1, 1)) * (20 + 55 * s)
    im = im.rotate(aci, resample=Image.BICUBIC, expand=False, fillcolor=tuple(int(v) for v in c["zemin"]))
    return dizi(im)


BOZUNMALAR = {
    "normal":       ([], (0.0, 0.0)),
    "hafif_toz":    ([bz_toz], (0.15, 0.40)),
    "toz":          ([bz_toz], (0.60, 1.00)),
    "yari_silik":   ([bz_yari_silik], (0.40, 1.00)),
    "silik":        ([bz_sil], (0.45, 0.85)),
    "cizik":        ([bz_cizik], (0.30, 1.00)),
    "leke":         ([bz_leke], (0.30, 1.00)),
    "bulanik":      ([bz_bulanik], (0.05, 0.75)),
    "parlama":      ([bz_parlama], (0.30, 1.00)),
    "kismi_kapali": ([bz_kismi_kapali], (0.30, 1.00)),
    "acili":        ([bz_acili], (0.30, 1.00)),
    "capraz":       ([bz_capraz], (0.30, 1.00)),
    "karisik":      (None, (0.30, 0.85)),  # 2-3 rastgele bozunma birlikte
}
TUM_TURLER = list(BOZUNMALAR)
KARISIK_HAVUZ = [bz_toz, bz_yari_silik, bz_sil, bz_cizik, bz_leke, bz_bulanik, bz_parlama, bz_kismi_kapali, bz_acili,
                 bz_capraz]


def bozunma_uygula(arr, ctx, tur, siddet):
    fonksiyonlar, _ = BOZUNMALAR[tur]
    if tur == "karisik":
        fonksiyonlar = ctx["rng"].sample(KARISIK_HAVUZ, ctx["rng"].choice([2, 3]))
    for f in fonksiyonlar:
        arr = f(arr, ctx, siddet)
    # kamera/baskı gürültüsü (her örnekte hafif)
    sigma = 2 + 10 * siddet
    arr = arr + ctx["nrng"].normal(0, sigma, arr.shape[:2])[..., None]
    return np.clip(arr, 0, 255)


# --------------------------------------------------------------------------------------
# Okunabilirlik testi (OpenCV) ve kamera simülasyonu
# --------------------------------------------------------------------------------------


def oku(img, beklenen, mod_px):
    """OpenCV ile QR çözmeyi dener (önce Aruco tabanlı, sonra klasik dedektör). Başarılıysa 1, değilse 0.
    Not: OpenCV her zaman gerçek bir barkod okuyucu kadar iyi değildir; sonuçlar kabaca bir alt sınır verir."""
    if not CV2_VAR:
        return None
    gri = np.asarray(img.convert("L"))
    dedektorler = []
    if hasattr(cv2, "QRCodeDetectorAruco"):
        dedektorler.append(cv2.QRCodeDetectorAruco())
    dedektorler.append(cv2.QRCodeDetector())
    for pad in (0, int(max(8, 4 * mod_px))):
        g = cv2.copyMakeBorder(gri, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255) if pad else gri
        for d in dedektorler:
            try:
                deger, _, _ = d.detectAndDecode(g)
            except cv2.error:
                continue
            if deger == beklenen:
                return 1
    return 0


def kamera_kucult(img, mod_px, hedef_ppm):
    """Etiketi, kodun her modülü 'hedef_ppm' piksele denk gelecek şekilde küçültür."""
    olcek = hedef_ppm / mod_px
    w, h = img.size
    kucuk = img.resize((max(8, int(w * olcek)), max(8, int(h * olcek))), Image.BOX)
    return kucuk.filter(ImageFilter.GaussianBlur(0.5))  # lens yumuşaklığı


# --------------------------------------------------------------------------------------
# A4 baskı sayfaları
# --------------------------------------------------------------------------------------


def baski_sayfalari(kayitlar, dpi, klasor):
    A4w, A4h = int(mm_px(210, dpi)), int(mm_px(297, dpi))
    kenar, bosluk = int(mm_px(10, dpi)), int(mm_px(5, dpi))
    alt_bant = int(mm_px(16, dpi))
    font = yazi_tipi(mm_px(2.6, dpi))
    font_b = yazi_tipi(mm_px(3.2, dpi))
    sayfalar = []

    def yeni_sayfa():
        sf = Image.new("L", (A4w, A4h), 255)
        d = ImageDraw.Draw(sf)
        d.text((kenar, kenar // 2), f"Barkod test sayfası {len(sayfalar) + 1} - yazdırırken %100 / Gerçek boyut "
               f"(Sığdır KAPALI)", font=font_b, fill=0)
        # 50 mm cetvel çubuğu
        y = A4h - alt_bant + int(mm_px(6, dpi))
        x = kenar
        for i in range(5):
            d.rectangle((x + i * mm_px(10, dpi), y, x + (i + 1) * mm_px(10, dpi), y + mm_px(2.5, dpi)),
                        fill=0 if i % 2 == 0 else 255, outline=0)
        d.text((x + mm_px(52, dpi), y - mm_px(0.5, dpi)), "50 mm (ölçeği bununla kontrol edin)", font=font, fill=0)
        sayfalar.append(sf)
        return sf, d

    sf, d = yeni_sayfa()
    x, y, satir_h = kenar, kenar + int(mm_px(6, dpi)), 0
    for k in kayitlar:
        im = k["goruntu"]
        w, h = im.size
        slot = w
        if x + slot > A4w - kenar:
            x, y, satir_h = kenar, y + satir_h + bosluk, 0
        if y + h > A4h - kenar - alt_bant:
            sf, d = yeni_sayfa()
            x, y, satir_h = kenar, kenar + int(mm_px(6, dpi)), 0
        sf.paste(im.convert("L"), (x, y))
        d.rectangle((x - 1, y - 1, x + w, y + h), outline=150)  # kesim kılavuzu
        x += slot + bosluk
        satir_h = max(satir_h, h)

    klasor.mkdir(parents=True, exist_ok=True)
    yollar = []
    for i, s in enumerate(sayfalar, 1):
        yol = klasor / f"baski_{i:02d}.png"
        s.save(yol, dpi=(dpi, dpi))
        yollar.append(yol)
    pdf = klasor / "baski_sayfalari.pdf"
    sayfalar[0].save(pdf, save_all=True, append_images=sayfalar[1:], resolution=dpi, quality=100)
    return yollar, pdf


def tum_pdf_olustur(cikti, dpi, hedef_klasor):
    """etiketler/ klasöründeki (tüm geçmiş çalıştırmalar dahil) her PNG'yi gerçek boyutuyla (dosyaya
    gömülü dpi) okuyup, referans fotoğraftaki gibi farklı boyutlardaki tüm örnekleri tek bir A4 PDF setine,
    ayrı bir klasöre basılır. (yollar, pdf) döner; hiç etiket yoksa (None, None)."""
    dosyalar = sorted((cikti / "etiketler").glob("*.png"))
    if not dosyalar:
        return None, None
    kayitlar = []
    for yol in dosyalar:
        parcalar = yol.stem.split("_")
        no = int(parcalar[0])
        qr_mm = float(parcalar[-1].replace("mm", ""))
        orta = parcalar[1:-1]
        if orta and orta[-1] in DUZEN_LISTESI:
            duzen, tur = orta[-1], "_".join(orta[:-1])
        else:
            duzen, tur = "-", "_".join(orta)
        im = Image.open(yol)
        im.load()
        kayitlar.append(dict(no=no, tur=tur, duzen=duzen, qr_mm=qr_mm, goruntu=im))
    return baski_sayfalari(kayitlar, dpi, hedef_klasor)


# --------------------------------------------------------------------------------------
# Ana akış
# --------------------------------------------------------------------------------------


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Silik / yarı silik / normal QR etiket örnekleri üretir.")
    ap.add_argument("--adet", type=int, default=60, help="üretilecek örnek sayısı (varsayılan 60)")
    ap.add_argument("--cikti", default="barkod_ciktilari", help="çıktı klasörü")
    ap.add_argument("--dpi", type=int, default=600, help="çözünürlük; baskı için 600 önerilir")
    ap.add_argument("--boyut", default="10,14,18,24,30",
                    help="QR kod kenar uzunlukları (mm), virgülle. Fotoğraftaki kod küçük olduğu için 10-30 mm")
    ap.add_argument("--tur", default="normal,yari_silik,silik,bulanik",
                    help="bozunma türleri, virgülle (varsayılan: tam görünüm/normal, yarı silik, silik, bulanık). "
                         "Tüm seçenekler için --tur hepsi kullanın. Seçenekler: " + ", ".join(TUM_TURLER))
    ap.add_argument("--duzen", default="hepsi",
                    help="metnin QR'a göre konumu, virgülle: sag, sol, ust, alt (varsayılan hepsi = rastgele karışık)")
    ap.add_argument("--duzeltme", default="M", choices=list(DUZELTME), help="QR hata düzeltme seviyesi")
    ap.add_argument("--yuk-uzunluk", type=int, default=70,
                    help="QR içindeki metin uzunluğu; büyüdükçe kod yoğunlaşır (fotoğraf gibi yoğun kod için 70-100)")
    ap.add_argument("--siddet", type=float, default=None, help="0-1 arası sabit bozunma şiddeti (boşsa rastgele)")
    ap.add_argument("--seed", type=int, default=42, help="aynı sayıyla aynı örnekler tekrar üretilir")
    ap.add_argument("--sayfa-yok", action="store_true", help="A4 baskı sayfalarını üretme")
    ap.add_argument("--tum-pdf", action="store_true",
                    help="klasördeki (geçmiş çalıştırmalar dahil) TÜM etiketleri, farklı boyutlarıyla, "
                         "ayrı bir 'tum_pdf' klasörüne tek PDF seti olarak basar")
    args = ap.parse_args()

    turler = TUM_TURLER if args.tur == "hepsi" else [t.strip() for t in args.tur.split(",")]
    for t in turler:
        if t not in BOZUNMALAR:
            sys.exit(f"Bilinmeyen tür: {t}. Seçenekler: {', '.join(TUM_TURLER)}")
    boyutlar = [float(b) for b in args.boyut.split(",")]
    duzenler = list(DUZEN_LISTESI) if args.duzen == "hepsi" else [d.strip() for d in args.duzen.split(",")]
    for d in duzenler:
        if d not in DUZEN_LISTESI:
            sys.exit(f"Bilinmeyen düzen: {d}. Seçenekler: {', '.join(DUZEN_LISTESI)}")

    cikti = Path(args.cikti)
    (cikti / "etiketler").mkdir(parents=True, exist_ok=True)
    if not CV2_VAR:
        print("Uyarı: opencv-python yok, okunabilirlik testi atlanacak (pip install opencv-python).")

    # klasörde zaten örnek varsa numaralandırmaya kaldığı yerden devam et (üstüne yazma, ekle)
    baslangic = len(list((cikti / "etiketler").glob("*.png")))

    kayitlar, satirlar = [], []
    ppm_basliklari = [f"okuma_{p}px_modul" for p in PPM_LISTESI]
    for i in range(args.adet):
        no = baslangic + i
        rng = random.Random(args.seed * 100003 + no)
        nrng = np.random.default_rng(args.seed * 100003 + no)
        tur = turler[no % len(turler)]
        duzen = duzenler[rng.randrange(len(duzenler))]
        qr_mm = boyutlar[(no // len(turler) + no) % len(boyutlar)] if len(boyutlar) > 1 else boyutlar[0]
        lo, hi = BOZUNMALAR[tur][1]
        siddet = args.siddet if args.siddet is not None else rng.uniform(lo, hi)

        parca, lot, yuk = rastgele_icerik(rng, args.yuk_uzunluk)
        matris = qr_matrisi(yuk, args.duzeltme)
        arr, ctx = temiz_etiket(rng, nrng, args.dpi, qr_mm, matris, parca, lot, duzen)
        arr = bozunma_uygula(arr, ctx, tur, siddet)
        im = pil(arr)

        ad = f"{no + 1:03d}_{tur}_{duzen}_{qr_mm:g}mm.png"
        im.save(cikti / "etiketler" / ad, dpi=(args.dpi, args.dpi))

        okuma_tam = oku(im, yuk, ctx["mod_px"])
        okuma_ppm = [oku(kamera_kucult(im, ctx["mod_px"], p), yuk, p) for p in PPM_LISTESI] if CV2_VAR else []

        satir = {
            "no": no + 1, "dosya": ad, "tur": tur, "siddet": round(siddet, 2), "qr_mm": qr_mm,
            "modul_sayisi": matris.shape[0], "modul_mm": round(qr_mm / matris.shape[0], 3),
            "etiket_genislik_mm": round(im.size[0] * 25.4 / args.dpi, 1),
            "etiket_yukseklik_mm": round(im.size[1] * 25.4 / args.dpi, 1),
            "parca_no": parca, "lot": lot, "icerik": yuk, "duzeltme": args.duzeltme,
            "okuma_tam_cozunurluk": okuma_tam,
        }
        for b, v in zip(ppm_basliklari, okuma_ppm):
            satir[b] = v
        satir["duzen"] = duzen  # eski (duzen sütunu olmayan) csv dosyalarıyla uyumlu kalsın diye en sona eklenir
        satirlar.append(satir)
        kayitlar.append(dict(no=no + 1, tur=tur, duzen=duzen, qr_mm=qr_mm, goruntu=im))
        print(f"[{no + 1:>3}/{baslangic + args.adet}] {ad:<42} siddet={siddet:.2f} modül={matris.shape[0]}x{matris.shape[0]} "
              f"okuma={okuma_tam}")

    # CSV (klasörde önceki çalıştırmalardan kalan ornekler.csv varsa üstüne eklenir, silinmez)
    if satirlar:
        csv_yolu = cikti / "ornekler.csv"
        onceden_var = csv_yolu.exists()
        with open(csv_yolu, "a" if onceden_var else "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(satirlar[0].keys()), delimiter=";")
            if not onceden_var:
                w.writeheader()
            w.writerows(satirlar)

        # Tür bazında özet (klasördeki TÜM örnekler üzerinden, önceki çalıştırmalar dahil)
        if CV2_VAR:
            with open(csv_yolu, encoding="utf-8-sig") as f:
                tum_satirlar = list(csv.DictReader(f, delimiter=";"))
            anahtarlar = ["okuma_tam_cozunurluk"] + ppm_basliklari
            turler_mevcut = sorted({s["tur"] for s in tum_satirlar},
                                    key=lambda t: TUM_TURLER.index(t) if t in TUM_TURLER else len(TUM_TURLER))
            with open(cikti / "ozet.csv", "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["tur", "adet"] + anahtarlar)
                print(f"\nOkuma oranı (%) - tür bazında (klasördeki toplam {len(tum_satirlar)} örnek)  |  "
                      "tam çözünürlük, " + ", ".join(f"{p}px/modül" for p in PPM_LISTESI))
                for t in turler_mevcut:
                    grup = [s for s in tum_satirlar if s["tur"] == t]
                    if not grup:
                        continue
                    oranlar = [round(100 * sum(int(s[a]) for s in grup) / len(grup)) for a in anahtarlar]
                    w.writerow([t, len(grup)] + oranlar)
                    print(f"  {t:<13} n={len(grup):<3} " + "  ".join(f"{o:>3}" for o in oranlar))

    # Baskı sayfaları (bu çalıştırmada yeni üretilenler)
    if not args.sayfa_yok and kayitlar:
        yollar, pdf = baski_sayfalari(kayitlar, args.dpi, cikti / "baskilar")
        print(f"\nBaskı sayfaları: {len(yollar)} adet A4  ->  {pdf}")

    # Tüm zamanların birleşik PDF'i, ayrı bir klasörde
    if args.tum_pdf:
        yollar, pdf = tum_pdf_olustur(cikti, args.dpi, cikti / "tum_pdf")
        if pdf:
            print(f"Tüm etiketlerden birleşik PDF: {len(yollar)} adet A4  ->  {pdf}")

    print(f"\nBitti. Klasör: {cikti.resolve()}")
    print("Not: parça no / lot / seri numaraları rastgele üretilmiştir.")


if __name__ == "__main__":
    main()
