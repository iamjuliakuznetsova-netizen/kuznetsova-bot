"""Пережать только картинки в PDF, не трогая текст, шрифты и ссылки.

Зачем отдельно от Ghostscript: gs пересобирает текстовый слой, и слова из
PDF-лид-магнитов (их копируют нажатием) рвутся на куски - "inflatable" -> "in"+"fl"+"atable".

Нужны pikepdf и Pillow (в requirements бота их нет, ставить в отдельный venv):
    python3 -m venv /tmp/pdfenv && /tmp/pdfenv/bin/pip install pikepdf pillow
    /tmp/pdfenv/bin/python -I tools/shrink_pdf_images.py <вход.pdf> <выход.pdf> 0.67 82

Для mishka (7,46 МБ): 0.67/82 -> 3,5 МБ, 0.58/80 -> 2,6 МБ. После сжатия сверить
текст: pdftotext -layout вход.pdf - | cmp - <(pdftotext -layout выход.pdf -)
"""
import io
import sys

import pikepdf
from PIL import Image

src, dst, scale, quality = sys.argv[1], sys.argv[2], float(sys.argv[3]), int(sys.argv[4])
pdf = pikepdf.open(src)
seen, before, after = set(), 0, 0

for page in pdf.pages:
    for name, xobj in page.images.items():
        if xobj.objgen in seen:
            continue
        seen.add(xobj.objgen)
        if xobj.get("/Filter") != pikepdf.Name.DCTDecode or "/SMask" in xobj or "/Mask" in xobj:
            continue  # трогаем только обычные JPEG без прозрачности
        raw = xobj.read_raw_bytes()
        img = Image.open(io.BytesIO(raw))
        icc = img.info.get("icc_profile")
        new_size = (round(img.width * scale), round(img.height * scale))
        small = img.convert("RGB").resize(new_size, Image.LANCZOS)
        out = io.BytesIO()
        small.save(out, "JPEG", quality=quality, optimize=True, progressive=False, icc_profile=icc)
        data = out.getvalue()
        before += len(raw)
        if len(data) >= len(raw):
            after += len(raw)
            continue
        xobj.write(data, filter=pikepdf.Name.DCTDecode)
        xobj.Width, xobj.Height = new_size
        after += len(data)

pdf.save(dst, compress_streams=True, object_stream_mode=pikepdf.ObjectStreamMode.generate)
print(f"уникальных картинок: {len(seen)}; их объём {before/1e6:.2f} МБ -> {after/1e6:.2f} МБ")
