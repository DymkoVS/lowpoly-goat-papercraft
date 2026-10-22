"""Развёртка замкнутой треугольной сетки в плоские детали для склейки из бумаги.

Этапы:
  1. Грани заранее размечены по зонам (тело, шея, голова, ноги…).
     Внутри каждой зоны жадно «выращиваем» детали: от крупной грани
     присоединяем соседей через самые выгодные рёбра (плоские, длинные,
     близко к центру детали), проверяя, что треугольник не налезает на уже
     уложенные, не образует узкой щели и деталь помещается на лист.
  2. Мелкие детали пришиваем к соседним (сначала в своей зоне, потом
     в любой), затем пробуем объединить родственные зоны (голова+уши+рога…).
  3. На разрезанных рёбрах — клапаны для клея и парные номера.
  4. Сгибы: выпуклое ребро — «гора», вогнутое — «долина»
     (печатная сторона — наружная поверхность модели).

Все координаты развёртки — в миллиметрах.
"""
import heapq
from dataclasses import dataclass, field

import numpy as np
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union

TOL = 0.05  # мм — совпадение точек на развёртке
MIN_GAP = 15.0  # град — самая узкая допустимая щель внутри детали


@dataclass
class Island:
    faces: dict = field(default_factory=dict)  # face -> (3, 2) координаты вершин грани
    poly: object = None  # объединение треугольников (shapely)
    region: str = ""
    name: str = ""
    side: str = ""
    tabs: list = field(default_factory=list)  # [(edge_id, Polygon, edge, face)]


def tri_overlap(A, B, eps=0.05):
    """Перекрываются ли треугольники A и B (3x2) по площади — теорема о разделяющей оси.

    Касание по ребру или вершине (и зазор/нахлёст меньше eps мм) — не перекрытие.
    Своя проверка вместо shapely: GEOS на почти совпадающих вершинах
    (расхождение ~1e-14) иногда возвращает площадь целого треугольника.
    """
    for T in (A, B):
        for i in range(3):
            d = T[(i + 1) % 3] - T[i]
            n = np.array([-d[1], d[0]])
            ln = np.hypot(*n)
            if ln < 1e-12:
                continue
            n = n / ln
            pa, pb = A @ n, B @ n
            if pa.max() <= pb.min() + eps or pb.max() <= pa.min() + eps:
                return False
    return True


def overlaps(tris, coords):
    """Налезает ли хоть один треугольник из tris на треугольники детали coords."""
    for A in tris:
        x0, y0 = A.min(axis=0)
        x1, y1 = A.max(axis=0)
        for P in coords.values():
            if P[:, 0].max() < x0 or P[:, 0].min() > x1 or P[:, 1].max() < y0 or P[:, 1].min() > y1:
                continue
            if tri_overlap(A, P):
                return True
    return False


def _angle(v1, v2):
    return np.degrees(np.arccos(np.clip(v1 @ v2 / np.linalg.norm(v1) / np.linalg.norm(v2), -1, 1)))


class Unfolder:
    def __init__(self, mesh, regions=None, scale=10.0, max_w=190.0, max_h=277.0, tab_h=7.0,
                 seed=None, noise=0.0, groups=None):
        self.rng = np.random.default_rng(seed)
        self.noise = noise
        self.perim_scale = 400.0  # мм периметра, равноценные одной лишней детали
        self.w = (0.6, 0.35, 0.15)  # веса: двугранный угол, удалённость от центра, длина ребра
        self.m = mesh
        self.V = mesh.vertices * scale  # мм
        self.F = mesh.faces
        self.max_w, self.max_h, self.tab_h = max_w, max_h, tab_h
        n = len(self.F)
        self.regions = regions or ["all"] * n
        self.groups = groups or {}
        self.edge_faces = {}
        for fi, f in enumerate(self.F):
            for k in range(3):
                e = tuple(sorted((int(f[k]), int(f[(k + 1) % 3]))))
                self.edge_faces.setdefault(e, []).append(fi)
        assert all(len(v) == 2 for v in self.edge_faces.values()), "сетка не замкнута"
        self.neighbors = [[] for _ in range(n)]
        for e, (f1, f2) in self.edge_faces.items():
            self.neighbors[f1].append((f2, e))
            self.neighbors[f2].append((f1, e))
        self.dihedral, self.convex = {}, {}
        fn = mesh.face_normals
        for e, (f1, f2) in self.edge_faces.items():
            self.dihedral[e] = np.degrees(np.arccos(np.clip(fn[f1] @ fn[f2], -1, 1)))
            c2 = self.V[[v for v in self.F[f2] if v not in e][0]]
            # выпукло, если третья вершина соседней грани лежит «под» плоскостью f1
            self.convex[e] = (c2 - self.V[e[0]]) @ fn[f1] < 0
        self.area = mesh.area_faces * scale * scale
        self.face_island = -np.ones(n, dtype=int)
        self.islands = []

    # ------------------------------------------------------------ геометрия

    def place_seed(self, f):
        a, b, c = self.V[self.F[f]]
        ab = np.linalg.norm(b - a)
        ac = c - a
        x = ac @ (b - a) / ab
        y = np.sqrt(max(ac @ ac - x * x, 0))
        return np.array([[0, 0], [ab, 0], [x, y]])

    def place_neighbor(self, f, P, g, e):
        """2D-координаты грани g, присоединённой к уложенной грани f по ребру e."""
        Ff, Fg = list(self.F[f]), list(self.F[g])
        a, b = e
        pa, pb = P[Ff.index(a)], P[Ff.index(b)]
        pc_f = P[[i for i in range(3) if Ff[i] not in e][0]]
        c = [v for v in Fg if v not in e][0]
        A, B, C = self.V[a], self.V[b], self.V[c]
        lab = np.linalg.norm(B - A)
        x = (C - A) @ (B - A) / lab
        y = np.sqrt(max((C - A) @ (C - A) - x * x, 0))
        u = (pb - pa) / np.linalg.norm(pb - pa)
        nrm = np.array([-u[1], u[0]])
        side = np.sign((pc_f - pa) @ nrm)
        pc = pa + x * u - side * y * nrm
        Q = np.zeros((3, 2))
        Q[Fg.index(a)], Q[Fg.index(b)], Q[Fg.index(c)] = pa, pb, pc
        return Q

    def edge_2d(self, coords, f, e):
        P = coords[f]
        Ff = list(self.F[f])
        return P[Ff.index(e[0])], P[Ff.index(e[1])]

    def fits(self, poly):
        r = poly.minimum_rotated_rectangle
        pts = np.asarray(r.exterior.coords)[:4]
        w, h = sorted((np.linalg.norm(pts[1] - pts[0]), np.linalg.norm(pts[2] - pts[1])))
        m = 2 * self.tab_h
        return w <= self.max_w - m and h <= self.max_h - m

    def slit_between(self, coords, f, g, e):
        """True, если ребро e между гранями f и g одной детали разошлось узкой щелью."""
        fa, fb = self.edge_2d(coords, f, e)
        ga, gb = self.edge_2d(coords, g, e)
        da, db = np.linalg.norm(fa - ga), np.linalg.norm(fb - gb)
        if da < TOL and db < TOL:
            return False  # сомкнулось — обычный сгиб
        if da < TOL:
            return _angle(fb - fa, gb - fa) < MIN_GAP
        if db < TOL:
            return _angle(fa - fb, ga - fb) < MIN_GAP
        return False

    # ------------------------------------------------------------ рост деталей

    def edge_cost(self, e, centroid, Q):
        length = np.linalg.norm(self.V[e[0]] - self.V[e[1]])
        dist = np.linalg.norm(Q.mean(axis=0) - centroid)
        jitter = self.rng.normal(0, self.noise) if self.noise else 0.0
        wd, wc, wl = self.w
        return self.dihedral[e] * wd + dist * wc - length * wl + jitter

    def grow(self, seed):
        isl = Island(region=self.regions[seed])
        P = self.place_seed(seed)
        isl.faces[seed] = P
        isl.poly = Polygon(P)
        idx = len(self.islands)
        self.face_island[seed] = idx
        heap = []
        counter = 0

        def push(f):
            nonlocal counter
            cen = np.array(isl.poly.centroid.coords[0])
            for g, e in self.neighbors[f]:
                if self.face_island[g] >= 0 or self.regions[g] != isl.region:
                    continue
                Q = self.place_neighbor(f, isl.faces[f], g, e)
                heapq.heappush(heap, (self.edge_cost(e, cen, Q), counter, f, g, e))
                counter += 1

        push(seed)
        while heap:
            _, _, f, g, e = heapq.heappop(heap)
            if self.face_island[g] >= 0:
                continue
            Q = self.place_neighbor(f, isl.faces[f], g, e)
            tri = Polygon(Q)
            if overlaps([Q], isl.faces):
                continue
            isl.faces[g] = Q
            if any(self.face_island[h] == idx and self.slit_between(isl.faces, g, h, e2)
                   for h, e2 in self.neighbors[g] if e2 != e):
                del isl.faces[g]
                continue
            new_poly = isl.poly.union(tri)
            if not self.fits(new_poly):
                del isl.faces[g]
                continue
            isl.poly = new_poly
            self.face_island[g] = idx
            push(g)
        self.islands.append(isl)
        return isl

    def _region_score(self, isls):
        sizes = [len(i.faces) for i in isls if i.faces]
        # периметр деталей (длина резки и клапанов) — мера «аккуратности» формы
        perim = sum(i.poly.length for i in isls if i.faces)
        return (len(sizes) + 2.5 * sum(1 for x in sizes if x <= 2) + 1.0 * sum(1 for x in sizes if x == 3)
                + perim / self.perim_scale)

    def _unfold_faces(self, faces, region):
        """Одна попытка: разложить грани одной зоны (жадный рост + слияние мелочи)."""
        start = len(self.islands)
        jit = 1 + self.rng.uniform(0, 0.5, len(faces))
        for f in np.asarray(faces)[np.argsort(-self.area[faces] * jit)]:
            if self.face_island[f] < 0:
                self.grow(f)
        mine = set(range(start, len(self.islands)))
        self.merge(lambda s, b: True, only=mine)
        return [self.islands[i] for i in mine]

    def _trial_params(self, t):
        """Параметры попытки t: веса стоимости и шум (t = 0 — без шума)."""
        self.rng = np.random.default_rng(t)
        if t == 0:
            self.noise, self.w = 0.0, (0.6, 0.35, 0.15)
        else:
            self.noise = self.rng.uniform(0.5, 6)
            self.w = (self.rng.uniform(0.1, 1.5), self.rng.uniform(0, 0.6), self.rng.uniform(0, 0.6))

    def unfold_symmetric(self, tries=150, merge_groups=True):
        """Развёртка левой половины по зонам с подбором лучшей попытки + зеркало справа."""
        cen = self.m.triangles_center
        left = np.where(cen[:, 1] > 0)[0]
        # зоны левой половины; грани правой половины не трогаем
        for f in np.where(cen[:, 1] <= 0)[0]:
            self.face_island[f] = -2
        by_region = {}
        for f in left:
            by_region.setdefault(self.regions[f].split(":")[0], []).append(f)
        for name, faces in by_region.items():
            for f in faces:
                self.regions[f] = name
            best = None
            for t in range(tries):
                saved_fi, saved_n = self.face_island.copy(), len(self.islands)
                self._trial_params(t)
                isls = self._unfold_faces(faces, name)
                sc = self._region_score(isls)
                if best is None or sc < best[0]:
                    best = (sc, t)
                self.face_island, self.islands = saved_fi, self.islands[:saved_n]
            self._trial_params(best[1])
            self._unfold_faces(faces, name)
        self.compact_keep()
        if merge_groups:
            self.noise = 0.0
            self.merge(lambda s, b: self.groups.get(s.region) is not None
                       and self.groups.get(s.region) == self.groups.get(b.region))
            self.merge(lambda s, b: len(s.faces) <= 3)
            self.compact_keep()
        self.mirror_right()
        return self.islands

    def compact_keep(self):
        """Убрать опустевшие детали, сохранив пометку -2 у граней правой половины."""
        self.islands = [i for i in self.islands if i.faces]
        for idx, isl in enumerate(self.islands):
            for f in isl.faces:
                self.face_island[f] = idx

    def mirror_right(self):
        """Правые детали — зеркальные копии левых."""
        V = self.m.vertices
        key = lambda p: tuple(np.round(p, 3))
        vid = {key(p): i for i, p in enumerate(V)}
        vmirror = np.array([vid[key(p * [1, -1, 1])] for p in V])
        fid = {tuple(sorted(f)): i for i, f in enumerate(self.F.tolist())}
        n_left = len(self.islands)
        for isl in self.islands[:n_left]:
            isl.side = "L"
            new = Island(region=isl.region)
            new.side = "R"
            for f, P in isl.faces.items():
                fv = list(self.F[f])
                g = fid[tuple(sorted(vmirror[fv]))]
                gv = list(self.F[g])
                Q = np.zeros((3, 2))
                for k in range(3):
                    Q[gv.index(vmirror[fv[k]])] = P[k] * [-1, 1]
                new.faces[g] = Q
            new.poly = unary_union([Polygon(q) for q in new.faces.values()])
            self.islands.append(new)
        self.compact()

    def unfold(self):
        jit = 1 + self.rng.uniform(0, self.noise / 10, len(self.area))
        for f in np.argsort(-self.area * jit):
            if self.face_island[f] < 0:
                self.grow(f)
        self.merge(lambda s, b: len(s.faces) <= 6 and s.region == b.region)
        self.merge(lambda s, b: len(s.faces) <= 4)
        self.merge(lambda s, b: self.groups.get(s.region.split(":")[0]) is not None
                   and self.groups.get(s.region.split(":")[0]) == self.groups.get(b.region.split(":")[0])
                   and s.region.split(":")[1] in (b.region.split(":")[1], "C"))
        self.compact()
        return self.islands

    # ------------------------------------------------------------ слияние

    def try_attach(self, si, bi):
        """Пришить деталь si к bi по одному из общих рёбер (поворот + сдвиг)."""
        small, big = self.islands[si], self.islands[bi]
        links = [(f, g, e) for f in small.faces for g, e in self.neighbors[f] if self.face_island[g] == bi]
        # сначала длинные общие рёбра
        links.sort(key=lambda t: -np.linalg.norm(self.V[t[2][0]] - self.V[t[2][1]]))
        for f, g, e in links:
            a0, b0 = self.edge_2d(small.faces, f, e)
            a1, b1 = self.edge_2d(big.faces, g, e)
            ang = np.arctan2(*(b1 - a1)[::-1]) - np.arctan2(*(b0 - a0)[::-1])
            R = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
            moved = {k: (v - a0) @ R.T + a1 for k, v in small.faces.items()}
            poly = unary_union([Polygon(v) for v in moved.values()])
            if overlaps(list(moved.values()), big.faces):
                continue
            merged = big.poly.union(poly)
            if not self.fits(merged):
                continue
            coords = {**big.faces, **moved}
            if any(self.slit_between(coords, f2, g2, e2)
                   for f2 in moved for g2, e2 in self.neighbors[f2] if g2 in big.faces):
                continue
            big.faces.update(moved)
            big.poly = merged
            for k in moved:
                self.face_island[k] = bi
            small.faces = {}
            return True
        return False

    def merge(self, allowed, only=None):
        changed = True
        while changed:
            changed = False
            order = sorted(range(len(self.islands)), key=lambda i: len(self.islands[i].faces))
            for si in order:
                if only is not None and si not in only:
                    continue
                s = self.islands[si]
                if not s.faces:
                    continue
                cand = {self.face_island[g] for f in s.faces for g, _ in self.neighbors[f]} - {si, -1, -2}
                if only is not None:
                    cand &= only
                for bi in sorted(cand, key=lambda i: -len(self.islands[i].faces)):
                    b = self.islands[bi]
                    if len(b.faces) < len(s.faces) or not allowed(s, b):
                        continue
                    if self.try_attach(si, bi):
                        changed = True
                        break
                if changed:
                    break

    def compact(self):
        self.islands = [i for i in self.islands if i.faces]
        for idx, isl in enumerate(self.islands):
            for f in isl.faces:
                self.face_island[f] = idx

    # ------------------------------------------------------------ рёбра, клапаны

    def classify_edges(self):
        """Для каждого ребра: 'fold' (сгиб внутри детали) или 'cut' (разрез)."""
        self.edge_kind = {}
        for e, (f1, f2) in self.edge_faces.items():
            i1, i2 = self.face_island[f1], self.face_island[f2]
            kind = "cut"
            if i1 == i2:
                c = self.islands[i1].faces
                a1, b1 = self.edge_2d(c, f1, e)
                a2, b2 = self.edge_2d(c, f2, e)
                if np.linalg.norm(a1 - a2) < TOL and np.linalg.norm(b1 - b2) < TOL:
                    kind = "fold"
            self.edge_kind[e] = kind
        return self.edge_kind

    def tab_polygon(self, isl, f, e, h, other_face):
        """Трапеция клапана на ребре e грани f, наружу от грани.

        Скосы не круче углов ответной грани, чтобы клапан не вылезал за неё.
        """
        pa, pb = self.edge_2d(isl.faces, f, e)
        P = isl.faces[f]
        Ff = list(self.F[f])
        pc = P[[i for i in range(3) if Ff[i] not in e][0]]
        d = pb - pa
        L = np.linalg.norm(d)
        u = d / L
        n = np.array([-u[1], u[0]])
        if (pc - pa) @ n > 0:
            n = -n
        Fo = list(self.F[other_face])
        A, B = self.V[e[0]], self.V[e[1]]
        C = self.V[[v for v in Fo if v not in e][0]]
        aa = np.radians(min(_angle(B - A, C - A), 50))
        ab = np.radians(min(_angle(A - B, C - B), 50))
        h = min(h, 0.45 * L)
        ta, tb = h / np.tan(max(aa, 0.2)), h / np.tan(max(ab, 0.2))
        if ta + tb > L - 1.0:
            k = (L - 1.0) / (ta + tb)
            ta, tb, h = ta * k, tb * k, h * k
        return Polygon([pa, pb, pb + h * n - tb * u, pa + h * n + ta * u])

    def make_tabs(self):
        cuts = [e for e, k in self.edge_kind.items() if k == "cut"]
        # нумеруем по порядку деталей — номера идут подряд
        cuts.sort(key=lambda e: tuple(sorted((self.face_island[self.edge_faces[e][0]],
                                              self.face_island[self.edge_faces[e][1]]))))
        self.cut_ids = {e: i for i, e in enumerate(cuts, 1)}
        self.tab_side = {}
        for isl in self.islands:
            isl.tabs = []
        tri = {f: Polygon(P) for isl in self.islands for f, P in isl.faces.items()}
        # короткие рёбра — первыми: им труднее всего найти место
        for e in sorted(cuts, key=lambda e: np.linalg.norm(self.V[e[0]] - self.V[e[1]])):
            f1, f2 = self.edge_faces[e]
            sides = [(f1, f2), (f2, f1)]
            if self.face_island[f2] < self.face_island[f1]:
                sides.reverse()
            best = None
            for f, g in sides:
                ii = self.face_island[f]
                isl = self.islands[ii]
                tp = self.tab_polygon(isl, f, e, self.tab_h, g)
                if tp.area < 1.0:
                    continue
                others = [tri[k] for k in isl.faces if k != f] + [t[1] for t in isl.tabs]
                obst = unary_union(others).buffer(0.6) if others else Polygon()
                clipped = tp.difference(obst).difference(tri[f])
                if clipped.is_empty:
                    continue
                if clipped.geom_type != "Polygon":
                    # кусок, прилегающий к ребру
                    pa, pb = self.edge_2d(isl.faces, f, e)
                    from shapely.geometry import LineString
                    base = LineString([pa, pb]).buffer(0.3)
                    parts = [p for p in clipped.geoms if p.intersects(base)]
                    if not parts:
                        continue
                    clipped = max(parts, key=lambda p: p.area)
                frac = clipped.area / tp.area
                if frac < 0.3 or clipped.area < 6.0:
                    continue
                if best is None or frac > best[0] + 0.15:
                    best = (frac, f, clipped.simplify(0.05))
            if best is None:
                self.tab_side[e] = None
                continue
            _, f, poly = best
            isl = self.islands[self.face_island[f]]
            isl.tabs.append((self.cut_ids[e], poly, e, f))
            self.tab_side[e] = f

    def outline(self, isl):
        return unary_union([isl.poly] + [t[1] for t in isl.tabs])

    def run(self, symmetric=True, tries=150):
        if symmetric:
            self.unfold_symmetric(tries)
        else:
            self.unfold()
        self.classify_edges()
        self.make_tabs()
        return self


def transform_island(isl, angle_deg, dx, dy):
    """Повернуть (вокруг начала координат) и сдвинуть деталь."""
    t = np.radians(angle_deg)
    R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    isl.faces = {k: v @ R.T + [dx, dy] for k, v in isl.faces.items()}
    isl.poly = affinity.translate(affinity.rotate(isl.poly, angle_deg, origin=(0, 0)), dx, dy)
    isl.tabs = [(i, affinity.translate(affinity.rotate(p, angle_deg, origin=(0, 0)), dx, dy), e, f)
                for i, p, e, f in isl.tabs]


def score(u):
    """Чем меньше, тем лучше: деталей, мелочи, рёбер без клапана, длина разрезов."""
    sizes = [len(i.faces) for i in u.islands]
    small = sum(1 for s in sizes if s <= 3)
    notab = sum(1 for v in u.tab_side.values() if v is None)
    cutlen = sum(np.linalg.norm(u.V[e[0]] - u.V[e[1]]) for e, k in u.edge_kind.items() if k == "cut")
    return len(sizes) + 3 * small + 4 * notab + cutlen / 500


def best_unfold(mesh, tries=100, **kw):
    best = None
    for t in range(tries):
        u = Unfolder(mesh, seed=t, noise=0.0 if t == 0 else 4.0, **kw).run()
        sc = score(u)
        if best is None or sc < best[0]:
            best = (sc, t, u)
    return best
