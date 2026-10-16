# Kumaş numune arşivi: Serge Ferrari (Soltis) ve Copaco (Serge 600) sitelerinden renk
# numunelerini koduyla indirir, küçük JPEG'e çevirir, ortalama rengini çıkarır.
# Çıktı: seri başına iki sprite (assets/kumas/{seri}-numune.jpg, {seri}-doku.jpg) ve
# assets/kumas/kumaslar.js (window.KUMASLAR: kod → ad, ortalama renk, sprite sırası).
# Uygulama çalışırken internete çıkmaz; bu araç arşivi güncellemek için elle koşulur:
#   python3 tools/kumas_arsivi.py
import base64, html, io, json, pathlib, re, sys, time, urllib.request
from PIL import Image, ImageChops, ImageFilter

root = pathlib.Path(__file__).resolve().parent.parent
OUT = root / "assets" / "kumas"
UA = {"User-Agent": "Mozilla/5.0 (ferrini-pozcizer kumas arsivi)"}
SIZE, QUALITY = 96, 84            # numune 96 px: kartta 22 px gösterilir, 2x/3x ekran için yeter
TILE = 48                         # çizimdeki doku karosu (dikişsiz, ışığı düzlenmiş)
COLS = 8                          # sprite sütun sayısı

# Excel'deki kumaş türü → (kaynak, sayfa(lar)). Seri anahtarı uygulamadaki eşleştirmeyle aynı.
SF = "https://www.sergeferrari.com/en/products/soltis/"
CP = "https://www.copaco.be/en/screens/exterior-screen-solutions/out/"
SOURCES = {
    "SF86":   ("sf", [SF + "86-color-alu/"]),
    "SF92":   ("sf", [SF + "92-color-alu-opaque-alu/"]),
    "SF96":   ("sf", [SF + "96-color-proof/"]),
    "SF622":  ("sf", [SF + "622-opaque-color/"]),
    "COPACO": ("cp", [CP + "serge-600", CP + "serge-600-out-in-the-jungle",
                      CP + "serge-600-blockout-lunar", CP + "serge-600-blockout-solar"]),
}


def fetch(url, tries=8):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return r.read()
        except Exception as ex:                      # vekil bağlantıyı ara sıra kesiyor
            if k == tries - 1:
                raise
            time.sleep(2 + k)


def sf_swatches(page):
    """Serge Ferrari: renk listesi sayfaya gömülü base64 PNG; metin 'White 92-2044'."""
    s = page.decode("utf-8", "ignore")
    i = s.find("colors-list")
    for blk in re.split(r'<div class="list-el"', s[i:])[1:]:
        m = re.search(r'src="data:image/\w+;base64,([^"]+)"', blk)
        txt = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<img[^>]*>", "", blk)))).strip()
        c = re.search(r"(\d{2,3}|W?\d{2})-(\d{3,6})", txt)
        if not (m and c):
            continue
        name = txt[:c.start()].replace('role="listitem">', "").strip()
        yield c.group(2).lstrip("0") or "0", name, base64.b64decode(m.group(1))


def cp_swatches(page):
    """Copaco: kartta arka plan görseli + 'product_number' (6 hane) + renk adı."""
    s = page.decode("utf-8", "ignore")
    for blk in s.split("class='xib product_box")[1:]:
        img = re.search(r"background-image:url\(([^)]+)\)", blk)
        num = re.search(r"product_number'>(\d+)<", blk)
        name = re.search(r"product_group_name'>([^<]+)<", blk)
        if img and num:
            yield num.group(1).lstrip("0"), html.unescape(name.group(1) if name else ""), fetch(img.group(1))


def prepare(raw):
    """Numune (SIZE px kare) + dikişsiz doku karosu (TILE px) + ortalama renk."""
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = im.size; k = min(w, h)
    im = im.crop(((w - k) // 2, (h - k) // 2, (w + k) // 2, (h + k) // 2)).resize((SIZE, SIZE), Image.LANCZOS)
    c = im.crop((SIZE // 4, SIZE // 4, SIZE * 3 // 4, SIZE * 3 // 4)).resize((1, 1), Image.BOX).getpixel((0, 0))
    # Doku karosu: fotoğraftaki ışık/kıvrım (düşük frekans) çıkarılır, yalnız örgü kalır; ortalama
    # renge oturtulur ve ayna simetrisiyle dikişsiz yapılır. Döşenince kareli görünmez.
    core = im.crop((SIZE // 6, SIZE // 6, SIZE * 5 // 6, SIZE * 5 // 6))
    low = core.filter(ImageFilter.GaussianBlur(6))
    flat = ImageChops.add(ImageChops.subtract(core, low, offset=128), Image.new("RGB", core.size, c), offset=-128)
    half = flat.resize((TILE // 2, TILE // 2), Image.LANCZOS)
    tile = Image.new("RGB", (TILE, TILE))
    tile.paste(half, (0, 0)); tile.paste(half.transpose(Image.FLIP_LEFT_RIGHT), (TILE // 2, 0))
    tile.paste(tile.crop((0, 0, TILE, TILE // 2)).transpose(Image.FLIP_TOP_BOTTOM), (0, TILE // 2))
    return im, tile, "#%02x%02x%02x" % c


def sheet(images, cell, path, quality):
    """Seri başına tek görsel (sprite): Atlas eşitlemesi en çok 200 dosya kabul eder, tarayıcı da az istek yapar."""
    rows = (len(images) + COLS - 1) // COLS
    out = Image.new("RGB", (COLS * cell, max(rows, 1) * cell), "white")
    for i, im in enumerate(images):
        out.paste(im, ((i % COLS) * cell, (i // COLS) * cell))
    out.save(path, quality=quality, optimize=True, progressive=True)
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = {}
    for seri, (kind, pages) in SOURCES.items():
        items, thumbs, tiles = {}, [], []
        for url in pages:
            try:
                page = fetch(url)
            except Exception as ex:
                print(f"! {seri} {url}: {ex}", file=sys.stderr); continue
            for kod, name, raw in (sf_swatches(page) if kind == "sf" else cp_swatches(page)):
                if kod in items:
                    continue
                try:
                    im, tile, hx = prepare(raw)
                except Exception as ex:
                    print(f"! {seri} {kod}: {ex}", file=sys.stderr); continue
                items[kod] = {"ad": name, "hex": hx, "i": len(thumbs)}
                thumbs.append(im); tiles.append(tile)
        if not items:
            continue
        rows = sheet(thumbs, SIZE, OUT / f"{seri}-numune.jpg", QUALITY)
        sheet(tiles, TILE, OUT / f"{seri}-doku.jpg", 82)
        index[seri] = {"numune": f"assets/kumas/{seri}-numune.jpg", "doku": f"assets/kumas/{seri}-doku.jpg",
                       "cols": COLS, "rows": rows, "renkler": items}
        print(seri, len(items), "numune")
    js = "// tools/kumas_arsivi.py üretir; elle düzenlemeyin.\nwindow.KUMASLAR = " + json.dumps(index, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (OUT / "kumaslar.js").write_text(js, encoding="utf-8")


if __name__ == "__main__":
    main()
