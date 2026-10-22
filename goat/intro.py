"""Вводные страницы PDF: характеристики и карта сборки, легенда и порядок работы,
список деталей и как закрыть фигуру. Тексты — из i18n (RU/EN)."""
import os

from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth

import pdf
from i18n import T, piece_name
from layout import MARGIN, PAGE_H, PAGE_W

N_INTRO = 3
FONT, BOLD = pdf.FONT, pdf.BOLD


def _para(c, x, y, lines, size=9.5, lead=1.45, width=None):
    """Строки с переносом по ширине (мм); строка '**…' — жирная. Возвращает новую y (мм)."""
    width = width or (PAGE_W - x - MARGIN)
    for line in lines:
        f = FONT
        if line.startswith("**"):
            f, line = BOLD, line.strip("*")
        words, cur, rows = line.split(" "), "", []
        for w in words:
            t = (cur + " " + w).strip()
            if stringWidth(t, f, size) / mm > width and cur:
                rows.append(cur)
                cur = w
            else:
                cur = t
        rows.append(cur)
        c.setFont(f, size)
        for r in rows:
            c.drawString(x * mm, y * mm, r)
            y -= size * lead * 0.3528  # pt -> мм
        y -= 0.8
    return y


def _heading(c, y, text, size=14):
    c.setFont(BOLD, size)
    c.drawString(MARGIN * mm, y * mm, text)


def draw(c, stats, u, out_dir, lang):
    W, H = PAGE_W, PAGE_H
    cm = T("cm")
    # ---------------------------------------------------------- лист 1: характеристики и карта
    c.setFont(BOLD, 18)
    c.drawString(MARGIN * mm, (H - MARGIN - 8) * mm, T("title", version=stats["version"]))
    sx, sy, sz = stats["size_cm"]
    rows = [
        (T("row_withers"), f"{stats['withers_cm']} {cm}"),
        (T("row_size"), f"{sx} × {sy} × {sz} {cm}"),
        (T("row_faces"), str(stats["faces"])),
        (T("row_pieces"), T("val_pieces", n=stats["pieces"], pairs=stats["pieces"] // 2)),
        (T("row_cuts"), str(stats["cuts"])),
        (T("row_sheets"), str(stats["pages"])),
        (T("row_tab"), f"{stats['tab_mm']:g} {T('mm')}"),
        (T("row_material"), stats["material"][lang]),
    ]
    y = H - MARGIN - 18
    for k, v in rows:
        c.setFont(FONT, 9.5)
        c.drawString(MARGIN * mm, y * mm, k)
        c.setFont(BOLD, 9.5)
        c.drawString((MARGIN + 85) * mm, y * mm, v)
        y -= 5.2
    img = os.path.join(out_dir, f"assembly_map_{lang}.png")
    if os.path.exists(img):
        ih = min((W - 2 * MARGIN) * 14 / 11, y - MARGIN - 10)
        iw = ih * 11 / 14
        c.drawImage(img, ((W - iw) / 2) * mm, (y - 4 - ih) * mm, iw * mm, ih * mm)
        y -= ih + 8
    c.setFont(FONT, 8.5)
    c.drawString(MARGIN * mm, y * mm, T("map_caption"))
    c.showPage()

    # ---------------------------------------------------------- лист 2: обозначения и порядок
    y = H - MARGIN - 6
    _heading(c, y, T("legend_title"))
    y -= 9
    x0 = MARGIN
    legend = [("cut", T("legend_cut")), ("mountain", T("legend_mountain")), ("valley", T("legend_valley")),
              ("tab", T("legend_tab")), ("num", T("legend_num"))]
    for kind, text in legend:
        yy = (y + 1.2) * mm
        c.setLineWidth(1.0)
        c.setStrokeGray(0)
        c.setDash([])
        if kind in ("cut", "mountain", "valley"):
            c.setDash({"cut": [], "mountain": pdf.MOUNTAIN_DASH, "valley": pdf.VALLEY_DASH}[kind])
            c.line(x0 * mm, yy, (x0 + 18) * mm, yy)
        elif kind == "tab":
            c.setFillGray(pdf.TAB_GRAY)
            p = c.beginPath()
            p.moveTo(x0 * mm, (y - 1) * mm)
            p.lineTo((x0 + 18) * mm, (y - 1) * mm)
            p.lineTo((x0 + 14) * mm, (y + 3) * mm)
            p.lineTo((x0 + 4) * mm, (y + 3) * mm)
            p.close()
            c.drawPath(p, fill=1, stroke=1)
            c.setFillGray(0)
        else:
            c.setFont(FONT, 8)
            c.drawCentredString((x0 + 9) * mm, y * mm, "17")
        c.setDash([])
        _para(c, x0 + 24, y, [text], size=9.5, width=W - 2 * MARGIN - 24)
        y -= 9.5

    y -= 2
    _heading(c, y, T("steps_title"))
    y -= 7
    _para(c, MARGIN, y, T("steps"), size=9.5)
    c.showPage()

    # ---------------------------------------------------------- лист 3: детали и финальный шов
    y = H - MARGIN - 6
    _heading(c, y, T("list_title"))
    y -= 7
    n = len(u.islands) // 2
    col_w = (W - 2 * MARGIN) / 2
    per_col = (n + 1) // 2
    c.setFont(FONT, 8.5)
    regions = T("regions")
    for i in range(n):
        a, b = u.islands[i], u.islands[i + n]
        txt = T("piece_line", a=piece_name(a), b=piece_name(b), region=regions.get(a.region, a.region),
                faces=len(a.faces), sa=a.sheet + N_INTRO, sb=b.sheet + N_INTRO)
        col, row = divmod(i, per_col)
        c.drawString((MARGIN + col * col_w) * mm, (y - row * 4.4) * mm, txt)
    y -= per_col * 4.4 + 8
    _heading(c, y, T("close_title"))
    y -= 7
    nums = ", ".join(str(x) for x in stats["belly_seam"])
    _para(c, MARGIN, y, [s.format(nums=nums) for s in T("close_text")], size=9.5)
    c.showPage()
    return N_INTRO
