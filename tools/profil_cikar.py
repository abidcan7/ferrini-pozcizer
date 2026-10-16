# Kutu kesit PDF'lerinden dış konturu (mm) ve şeffaf PNG kesit görselini üretir.
from PIL import Image
import pymupdf, cv2, numpy as np, json, sys, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
DPI = 600
out = {}
for name in ["sharp", "soft", "wave"]:
    page = pymupdf.open(root / f"zipline neo {name}.pdf")[0]
    clip = pymupdf.Rect(110, 260, 540, 660)            # ölçü çizgileri dışarıda
    pix = page.get_pixmap(dpi=DPI, clip=clip)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    mask = (gray < 235).astype(np.uint8) * 255
    # sadece en büyük bağlı bileşen grubu (profil); küçük gürültüleri at
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    pxmm = (y1 - y0) / 110.0
    # yarık konumu: alt kenarda maskenin boş olduğu aralık
    row = mask[y1 - int(1.5 * pxmm), x0:x1 + 1] > 0
    gaps, run = [], None
    for i, v in enumerate(row):
        if not v and run is None: run = i
        if v and run is not None: gaps.append((run, i)); run = None
    slot = max(gaps, key=lambda g: g[1] - g[0])
    closed = mask.copy()
    cv2.line(closed, (x0 + slot[0] - 4, y1 - int(1.2 * pxmm)), (x0 + slot[1] + 4, y1 - int(1.2 * pxmm)), 255, int(2 * pxmm))
    # gerçek ince cidarlı kesit (yarık açık, iç boşluk dahil tek kontur)
    sc, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    sc = max(sc, key=cv2.contourArea)
    sc = cv2.approxPolyDP(sc, 0.12 * pxmm, True)[:, 0, :]
    section = [[round((x - x0) / pxmm, 2), round((y - y0) / pxmm, 2)] for x, y in sc]
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cnts, key=cv2.contourArea)
    c = cv2.approxPolyDP(c, 0.25 * pxmm, True)[:, 0, :]
    pts = [[round((x - x0) / pxmm, 2), round((y - y0) / pxmm, 2)] for x, y in c]
    out[name] = {"w": round((x1 - x0) / pxmm, 1), "h": 110, "outline": pts, "section": section,
                 "slot": [round(slot[0] / pxmm, 1), round(slot[1] / pxmm, 1)]}
    # şeffaf PNG: profil gövdesi
    rgba = np.dstack([img, np.where(gray < 245, 255, 0).astype(np.uint8)])[y0 - 8:y1 + 8, x0 - 8:x1 + 8]
    rgba = cv2.resize(rgba, None, fx=0.35, fy=0.35, interpolation=cv2.INTER_AREA)
    Image.fromarray(rgba).save(root / "assets" / f"kesit-{name}.png")   # cv2.imwrite Türkçe yolda sessizce başarısız
    print(name, out[name]["w"], len(pts), len(section), "slot", out[name]["slot"])
(root / "assets" / "profiller.json").write_text(json.dumps(out), encoding="utf-8")
# HTML'in file:// altında da okuyabilmesi için JS olarak da yaz
(root / "assets" / "profiller.js").write_text("window.PROFILLER = " + json.dumps(out) + ";\n", encoding="utf-8")
