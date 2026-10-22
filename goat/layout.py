"""Раскладка деталей на листы A4.

Детали укладываются по их настоящему контуру (с клапанами), а не по
прямоугольнику: занятость листа хранится растром 1 мм, допустимые позиции
для детали ищутся свёрткой (FFT) маски детали с маской занятости.
Деталь пробуется в нескольких поворотах; выбирается самая «верхне-левая»
позиция — так лист заполняется плотно.
"""
import numpy as np
from PIL import Image, ImageDraw
from scipy.signal import fftconvolve
from shapely import affinity

from unfold import transform_island

PAGE_W, PAGE_H = 210.0, 297.0  # мм
MARGIN = 10.0  # поля под лазерный принтер
HEADER = 9.0  # полоса заголовка вверху листа
AREA_W = PAGE_W - 2 * MARGIN
AREA_H = PAGE_H - 2 * MARGIN - HEADER
GAP = 2.0  # зазор между деталями, мм
RES = 1.0  # мм на пиксель растра


def _mask(poly):
    """Растровая маска контура (с зазором), начало — в левом нижнем углу bbox."""
    p = poly.buffer(GAP / 2 + 0.5, join_style=2)
    x0, y0, x1, y1 = p.bounds
    w, h = int(np.ceil((x1 - x0) / RES)) + 1, int(np.ceil((y1 - y0) / RES)) + 1
    img = Image.new("1", (w, h), 0)
    d = ImageDraw.Draw(img)
    geoms = getattr(p, "geoms", [p])
    for g in geoms:
        d.polygon([((x - x0) / RES, (y - y0) / RES) for x, y in g.exterior.coords], fill=1)
    # строка 0 маски — верх детали (y = y0 + h - 1), как и строка 0 листа — верх области
    return np.array(img, dtype=np.float32)[::-1].copy(), (x0, y0)


class Page:
    def __init__(self):
        self.w, self.h = int(AREA_W / RES), int(AREA_H / RES)
        self.occ = np.zeros((self.h, self.w), dtype=np.float32)
        self.items = []  # (island, outline)

    def find(self, mask):
        mh, mw = mask.shape
        if mh > self.h or mw > self.w:
            return None
        conv = fftconvolve(self.occ, mask[::-1, ::-1], mode="valid")
        free = np.argwhere(conv < 0.5)
        if not len(free):
            return None
        # сверху вниз (строка 0 — верх листа), затем слева направо
        k = np.lexsort((free[:, 1], free[:, 0]))[0]
        return tuple(free[k])

    def put(self, mask, pos):
        r, c = pos
        self.occ[r:r + mask.shape[0], c:c + mask.shape[1]] += mask


def pack(unf, islands, angles=range(0, 360, 15), presorted=False):
    """Разложить детали по листам. Детали сдвигаются в координаты листа (мм, y вверх).

    presorted=True — укладывать в переданном порядке (иначе — от крупных к мелким).
    """
    pages = []
    order = list(islands) if presorted else sorted(islands, key=lambda i: -unf.outline(i).area)
    for isl in order:
        outline = unf.outline(isl)
        # базовый угол — выравнивание по минимальному прямоугольнику
        rect = np.asarray(outline.minimum_rotated_rectangle.exterior.coords)
        base = np.degrees(np.arctan2(rect[1, 1] - rect[0, 1], rect[1, 0] - rect[0, 0]))
        cands = sorted({round((-base + a) % 360, 3) for a in (0, 90, 180, 270)} | {float(a) for a in angles})
        masks = []
        for a in cands:
            p = affinity.rotate(outline, a, origin=(0, 0))
            m, off = _mask(p)
            masks.append((a, m, off))
        placed = False
        for page in pages + [None]:
            if page is None:
                page = Page()
                pages.append(page)
            best = None
            for a, m, off in masks:
                pos = page.find(m)
                if pos is None:
                    continue
                key = (pos[0] + m.shape[0] * 0.5, pos[1])  # предпочитаем ниже «потолок» детали
                if best is None or key < best[0]:
                    best = (key, a, m, off, pos)
            if best is None:
                if not page.items:
                    raise RuntimeError("деталь не помещается на пустой лист")
                continue
            _, a, m, off, (r, c) = best
            page.put(m, (r, c))
            # строка r листа -> y = верх области - r; строка 0 маски -> y = y0 + (h - 1)
            x_mm = MARGIN + c * RES - off[0]
            top_mm = PAGE_H - MARGIN - HEADER - r * RES
            y_mm = top_mm - (off[1] + (m.shape[0] - 1) * RES)
            transform_island(isl, a, 0, 0)
            transform_island(isl, 0, x_mm, y_mm)
            page.items.append(isl)
            placed = True
            break
        assert placed
    return pages


def pack_best(unf, islands, tries=12, seed=0):
    """Несколько порядков укладки (крупные первыми, с разбросом) — берём наименьшее число листов."""
    import copy

    rng = np.random.default_rng(seed)
    area = np.array([unf.outline(i).area for i in islands])
    best = None
    for t in range(tries):
        jit = np.ones(len(islands)) if t == 0 else rng.uniform(0.5, 1.5, len(islands))
        order = [islands[j] for j in np.argsort(-area * jit)]
        trial = copy.deepcopy(order)
        try:
            pages = pack(unf, trial, presorted=True)
        except RuntimeError:
            continue
        # при равном числе листов — где последний лист заполнен меньше всего (его проще «освободить»)
        key = (len(pages), pages[-1].occ.sum())
        if best is None or key < best[0]:
            best = (key, order)
    if best is None:
        raise RuntimeError("детали не помещаются на лист: увеличьте --faces (мельче грани) "
                           "или уменьшите --height")
    # повторяем лучший порядок на настоящих деталях
    return pack(unf, best[1], presorted=True)
