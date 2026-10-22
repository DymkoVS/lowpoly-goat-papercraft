"""Вывод выкройки в PDF (A4, масштаб 1:1) через reportlab."""
import os

import numpy as np
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from i18n import T, piece_name
from layout import HEADER, MARGIN, PAGE_H, PAGE_W

# свободный шрифт с кириллицей (DejaVu, лицензия — fonts/LICENSE_DEJAVU) — одинаково на всех ОС
FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT, BOLD = "DejaVuSans", "DejaVuSans-Bold"
pdfmetrics.registerFont(TTFont(FONT, os.path.join(FONT_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont(BOLD, os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))

CUT_W = 0.6  # pt — линия реза
FOLD_W = 0.45  # pt — линия сгиба
FOLD_GRAY = 0.3
TAB_GRAY = 0.84
FLAT_DEG = 2.0  # двугранный угол меньше — грань плоская, линию сгиба не рисуем
MOUNTAIN_DASH = [3.2 * mm, 1.0 * mm, 0.6 * mm, 1.0 * mm]  # штрих-пунктир — «гора»
VALLEY_DASH = [1.8 * mm, 1.2 * mm]  # пунктир — «долина»


def _path(c, pts):
    p = c.beginPath()
    p.moveTo(pts[0][0] * mm, pts[0][1] * mm)
    for x, y in pts[1:]:
        p.lineTo(x * mm, y * mm)
    p.close()
    return p


def _line(c, a, b):
    c.line(a[0] * mm, a[1] * mm, b[0] * mm, b[1] * mm)


def _text_along(c, a, b, inside_pt, text, size):
    """Подпись вдоль ребра ab внутри грани (inside_pt — точка внутри грани).

    Текст никогда не стоит вверх ногами; если буквы «смотрят» к ребру,
    базовая линия отодвигается от ребра на высоту букв.
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    mid = (a + b) / 2
    u = (b - a) / np.linalg.norm(b - a)
    if u[0] < -1e-9 or (abs(u[0]) <= 1e-9 and u[1] < 0):
        u = -u  # читаемое направление: слева направо
    n = np.array([-u[1], u[0]])  # «вверх» для текста
    inward = 1.0 if (inside_pt - mid) @ n > 0 else -1.0
    cap = size * 0.72 / mm  # высота заглавных, мм
    gap = 0.8  # мм от ребра до букв
    # базовая линия: если буквы растут внутрь — на расстоянии gap, иначе gap + cap
    shift = gap if inward > 0 else gap + cap
    pos = mid + n * inward * shift
    c.saveState()
    c.translate(pos[0] * mm, pos[1] * mm)
    c.rotate(np.degrees(np.arctan2(u[1], u[0])))
    c.setFont(FONT, size)
    c.drawCentredString(0, 0, text)
    c.restoreState()


def draw_island(c, unf, isl):
    # клапаны
    c.setFillGray(TAB_GRAY)
    c.setStrokeGray(0)
    c.setLineWidth(CUT_W)
    for _, tp, _, _ in isl.tabs:
        pts = list(tp.exterior.coords)[:-1]
        c.drawPath(_path(c, pts), fill=1, stroke=1)
    # грани (белые) поверх, контур — рез
    c.setFillGray(1)
    for f, P in isl.faces.items():
        c.drawPath(_path(c, P), fill=1, stroke=0)
    # рёбра
    for f, P in isl.faces.items():
        Ff = [int(v) for v in unf.F[f]]
        for k in range(3):
            e = tuple(sorted((Ff[k], Ff[(k + 1) % 3])))
            a, b = P[k], P[(k + 1) % 3]
            kind = unf.edge_kind[e]
            c.setDash([])
            if kind == "fold":
                if Ff[k] > Ff[(k + 1) % 3]:
                    continue  # внутреннее ребро рисуем один раз
                if unf.dihedral[e] < FLAT_DEG:
                    continue
                c.setStrokeGray(FOLD_GRAY)
                c.setLineWidth(FOLD_W)
                c.setDash(MOUNTAIN_DASH if unf.convex[e] else VALLEY_DASH)
                _line(c, a, b)
            else:
                has_tab = unf.tab_side.get(e) == f
                if has_tab:
                    # основание клапана — сгиб «гора» (клапан уходит внутрь модели)
                    c.setStrokeGray(FOLD_GRAY)
                    c.setLineWidth(FOLD_W)
                    c.setDash(MOUNTAIN_DASH)
                else:
                    c.setStrokeGray(0)
                    c.setLineWidth(CUT_W)
                _line(c, a, b)
    c.setDash([])
    # номера рёбер
    c.setFillGray(0)
    for f, P in isl.faces.items():
        Ff = [int(v) for v in unf.F[f]]
        cen = P.mean(axis=0)
        for k in range(3):
            e = tuple(sorted((Ff[k], Ff[(k + 1) % 3])))
            if unf.edge_kind[e] != "cut":
                continue
            a, b = P[k], P[(k + 1) % 3]
            L = np.linalg.norm(b - a)
            size = 6.0 if L > 14 else 4.5
            _text_along(c, a, b, cen, str(unf.cut_ids[e]), size)
    # название детали — в самой крупной грани
    f = max(isl.faces, key=lambda k: unf.area[k])
    P = isl.faces[f]
    # точка, наиболее удалённая от сторон, — центр вписанной окружности
    la = np.linalg.norm(P[1] - P[2])
    lb = np.linalg.norm(P[2] - P[0])
    lc = np.linalg.norm(P[0] - P[1])
    inc = (la * P[0] + lb * P[1] + lc * P[2]) / (la + lb + lc)
    r_in = 2 * unf.area[f] / (la + lb + lc)
    size = float(np.clip(r_in * 1.1, 6, 14))
    c.setFont(BOLD, size)
    c.drawCentredString(inc[0] * mm, inc[1] * mm - size * 0.3, piece_name(isl))


def draw_header(c, title, page_no, total):
    y = (PAGE_H - MARGIN - HEADER + 3.0) * mm
    c.setFillGray(0)
    c.setFont(BOLD, 9)
    c.drawString(MARGIN * mm, y, title)
    c.setFont(FONT, 8)
    c.drawString((MARGIN + 52) * mm, y, T("sheet", i=page_no, n=total))
    # контрольный отрезок 50 мм
    x1 = PAGE_W - MARGIN
    x0 = x1 - 50
    c.setLineWidth(0.6)
    c.setStrokeGray(0)
    _line(c, (x0, (y / mm) + 0.5), (x1, (y / mm) + 0.5))
    for t in range(0, 51, 10):
        _line(c, (x0 + t, (y / mm) + 0.5), (x0 + t, (y / mm) + (2.2 if t % 50 == 0 else 1.4)))
    c.setFont(FONT, 6.5)
    c.drawCentredString((x0 + 25) * mm, y - 2.6 * mm, T("check50"))


def write_pattern(path, unf, pages, title, intro=None):
    """intro(c) — функция, рисующая вводные страницы (инструкцию)."""
    c = canvas.Canvas(path, pagesize=(PAGE_W * mm, PAGE_H * mm))
    c.setTitle(title)
    c.setAuthor("lowpoly-goat-papercraft")
    n_intro = 0
    if intro:
        n_intro = intro(c)
    total = n_intro + len(pages)
    for i, page in enumerate(pages, 1):
        draw_header(c, title, n_intro + i, total)
        for isl in page.items:
            draw_island(c, unf, isl)
        c.showPage()
    c.save()
