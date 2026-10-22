"""Процедурная low-poly модель козы.

Форма задаётся неявной функцией расстояния (SDF): туловище, шея, голова, ноги,
уши, рога, хвост — это эллипсоиды и «капсулы» переменного радиуса, слитые
плавным объединением. Поверхность извлекается marching cubes, затем
половина модели (y >= 0) упрощается квадрик-децимацией до low-poly и
зеркалится — так коза получается строго симметричной.

Единицы — сантиметры. Ось x — вперёд (к голове), y — влево, z — вверх,
пол — плоскость z = 0.
"""
import numpy as np
import pymeshlab
import trimesh
from skimage import measure

# ---------------------------------------------------------------- примитивы


def smin(a, b, k):
    """Плавное объединение двух SDF (k — радиус «перетекания», см)."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def round_cone(p, a, b, r1, r2, ys=1.0):
    """Капсула от точки a (радиус r1) до b (радиус r2).

    ys > 1 сплющивает примитив по оси y (делает его уже).
    """
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    q = p.copy()
    q[:, 1] = q[:, 1] * ys
    a = a * [1, ys, 1]
    b = b * [1, ys, 1]
    ab = b - a
    t = np.clip(((q - a) @ ab) / (ab @ ab), 0, 1)
    c = a + t[:, None] * ab
    r = r1 + (r2 - r1) * t
    return np.linalg.norm(q - c, axis=1) - r


def ellipsoid(p, c, r, rot=None):
    """Эллипсоид с центром c и полуосями r (rot — матрица поворота в локальные оси)."""
    q = p - np.asarray(c, float)
    if rot is not None:
        q = q @ rot
    r = np.asarray(r, float)
    k = np.linalg.norm(q / r, axis=1)
    return (k - 1.0) * r.min()


def rot_z(deg):
    t = np.radians(deg)
    return np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1]])


def rot_x(deg):
    t = np.radians(deg)
    return np.array([[1, 0, 0], [0, np.cos(t), -np.sin(t)], [0, np.sin(t), np.cos(t)]])


# ---------------------------------------------------------------- коза


def goat_parts(q):
    """SDF отдельных частей козы (q — точки с уже отражённой y >= 0).

    Возвращает список (имя части, sdf, радиус слияния с предыдущими).
    """
    # туловище: грудь, живот, круп
    body = ellipsoid(q, (9.0, 0, 22.3), (8.0, 5.6, 7.5))
    body = smin(body, ellipsoid(q, (-1.5, 0, 21.6), (11.5, 6.3, 7.3)), 3.0)
    body = smin(body, ellipsoid(q, (-12.0, 0, 23.5), (6.8, 5.5, 6.3)), 3.0)
    # грудь (подгрудок) выдаётся вперёд
    body = smin(body, ellipsoid(q, (14.0, 0, 21.5), (3.5, 4.3, 5.0)), 2.0)
    # холка и маклоки (тазовые бугры) — немного «рельефа» спины
    body = smin(body, ellipsoid(q, (9.0, 0, 27.6), (5.0, 2.6, 2.7)), 2.0)
    body = smin(body, ellipsoid(q, (-12.5, 3.0, 26.7), (3.0, 2.2, 2.2)), 2.0)

    # шея: широкая спереди-назад, сплющена с боков, стоит круто (~60°)
    neck = round_cone(q, (13.0, 0, 26.0), (18.8, 0, 37.0), 4.8, 3.0, ys=1.3)

    # голова: клин от затылка к морде + нижняя челюсть
    head = round_cone(q, (20.2, 0, 39.0), (29.4, 0, 34.0), 3.25, 1.8, ys=1.15)
    head = smin(head, round_cone(q, (21.5, 0, 36.6), (28.7, 0, 33.2), 2.3, 1.45, ys=1.2), 1.0)

    # борода
    beard = round_cone(q, (26.2, 0, 33.2), (25.6, 0, 29.8), 1.25, 0.5, ys=1.2)

    # уши: плоские, торчат в стороны, чуть назад и вниз
    ear_rot = rot_z(-20) @ rot_x(-20)
    ear = ellipsoid(q, (20.6, 4.9, 39.0), (1.5, 3.1, 0.6), ear_rot)

    # рога: дугой назад-вверх
    horn = round_cone(q, (20.6, 1.5, 41.3), (19.6, 1.9, 45.2), 1.0, 0.7)
    horn = np.minimum(horn, round_cone(q, (19.6, 1.9, 45.2), (16.8, 2.6, 47.6), 0.7, 0.35))

    # хвост: короткий, торчит вверх-назад
    tail = round_cone(q, (-17.5, 0, 27.0), (-20.0, 0, 30.5), 1.5, 0.7, ys=1.3)

    # передние ноги: плечо/предплечье, запястье, пясть, копыто
    fl = round_cone(q, (9.8, 3.4, 20.0), (10.4, 3.3, 9.5), 2.5, 1.5)
    fl = smin(fl, round_cone(q, (10.4, 3.3, 9.5), (10.6, 3.3, 2.0), 1.45, 1.25), 0.5)
    fl = smin(fl, round_cone(q, (10.6, 3.3, 2.0), (11.3, 3.3, 0.0), 1.3, 1.45), 0.4)

    # задние ноги: бедро, голень назад к скакательному суставу, плюсна, копыто
    hl = round_cone(q, (-10.5, 3.7, 22.0), (-9.8, 3.4, 13.5), 3.4, 1.85)
    hl = smin(hl, round_cone(q, (-9.8, 3.4, 13.5), (-13.2, 3.2, 8.0), 1.75, 1.3), 0.6)
    hl = smin(hl, round_cone(q, (-13.2, 3.2, 8.0), (-12.8, 3.2, 2.0), 1.3, 1.2), 0.4)
    hl = smin(hl, round_cone(q, (-12.8, 3.2, 2.0), (-12.1, 3.2, 0.0), 1.25, 1.45), 0.4)

    return [("body", body, 0), ("neck", neck, 2.5), ("head", head, 1.8), ("head", beard, 1.2),
            ("ear", ear, 0.6), ("horn", horn, 0.5), ("tail", tail, 1.0),
            ("fleg", fl, 1.8), ("hleg", hl, 2.0)]


def goat_sdf(p):
    """SDF козы для массива точек p (N x 3). Модель симметрична по y."""
    q = p.copy()
    q[:, 1] = np.abs(q[:, 1])  # симметрия: всё строим для y >= 0
    parts = goat_parts(q)
    d = parts[0][1]
    for _, sd, k in parts[1:]:
        d = smin(d, sd, k)
    # плоское дно копыт: срезаем всё ниже пола
    return np.maximum(d, -p[:, 2])


# названия зон для выкройки и инструкции
REGION_NAMES = {
    "body_f": "Тело, перёд", "body_r": "Тело, зад", "neck": "Шея", "head": "Голова",
    "ear": "Ухо", "horn": "Рог", "tail": "Хвост", "fleg": "Нога передняя", "hleg": "Нога задняя",
}


def withers_height(mesh):
    """Высота в холке: верх спины над передними ногами (модель в исходных осях)."""
    lo, hi = mesh.bounds
    L = hi[0] - lo[0]
    v = mesh.vertices
    x0 = lo[0] + 0.53 * L  # холка — примерно над передними ногами
    sel = (v[:, 0] > x0) & (v[:, 0] < x0 + 0.08 * L) & (np.abs(v[:, 1]) < 0.06 * L)
    return float(v[sel, 2].max())


def face_regions(mesh, body_split_x=-1.0, scale=1.0):
    """Зона каждой грани: ближайшая к центру грани часть модели + сторона (Л/П).

    scale — во сколько раз модель масштабирована относительно SDF.
    Возвращает список строк вида 'body_f:L', 'head:R', 'tail:C'.
    """
    c = mesh.triangles_center / scale
    q = c.copy()
    q[:, 1] = np.abs(q[:, 1])
    parts = goat_parts(q)
    names = [n for n, _, _ in parts]
    dist = np.stack([np.abs(sd) for _, sd, _ in parts], axis=1)
    best = dist.argmin(axis=1)
    out = []
    for i, b in enumerate(best):
        name = names[b]
        if name == "body":
            name = "body_f" if c[i, 0] > body_split_x else "body_r"
        side = "L" if c[i, 1] > 0 else "R"
        if name == "tail":
            side = "C"
        out.append(f"{name}:{side}")
    return out


# ---------------------------------------------------------------- сетка

BOUNDS = ((-23.0, 33.0), (-11.0, 11.0), (-0.5, 50.0))


def dense_half_mesh(step=0.15):
    """Плотная сетка правой половины (y >= 0) без «крышки» по плоскости симметрии."""
    (x0, x1), _, (z0, z1) = BOUNDS
    xs = np.arange(x0, x1, step)
    ys = np.arange(-2 * step, 11.0, step)
    zs = np.arange(z0, z1, step)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    pts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1).astype(np.float32)
    vol = goat_sdf(pts).reshape(X.shape)
    verts, faces, _, _ = measure.marching_cubes(vol, 0.0, spacing=(step, step, step))
    verts += [xs[0], ys[0], zs[0]]
    m = trimesh.Trimesh(verts, faces, process=True)
    # режем по y = 0, оставляем y >= 0
    m = m.slice_plane([0, 0, 0], [0, 1, 0], cap=False)
    return m


def decimate_half(m, target_faces):
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(np.ascontiguousarray(m.vertices, dtype=np.float64),
                                np.ascontiguousarray(m.faces, dtype=np.int32)))
    ms.meshing_remove_duplicate_vertices()
    ms.meshing_repair_non_manifold_edges()
    ms.meshing_repair_non_manifold_vertices()
    ms.meshing_decimation_quadric_edge_collapse(
        targetfacenum=int(target_faces),
        qualitythr=0.9,
        preserveboundary=False,
        preservenormal=True,
        optimalplacement=False,
        planarquadric=True,
        planarweight=0.002,
        autoclean=True,
    )
    out = ms.current_mesh()
    return trimesh.Trimesh(out.vertex_matrix(), out.face_matrix(), process=True)


def _min_angle(P):
    a, b, c = P
    out = []
    for u, v, w in ((a, b, c), (b, c, a), (c, a, b)):
        e1, e2 = v - u, w - u
        cosv = e1 @ e2 / (np.linalg.norm(e1) * np.linalg.norm(e2) + 1e-12)
        out.append(np.degrees(np.arccos(np.clip(cosv, -1, 1))))
    return min(out)


def _normal(P):
    n = np.cross(P[1] - P[0], P[2] - P[0])
    return n / (np.linalg.norm(n) + 1e-12)


def improve_slivers(m, max_dihedral=22.0, gain=3.0):
    """Переворот диагоналей у пар почти плоских треугольников ради бóльших углов.

    Убирает «иголки», которые неудобно вырезать и клеить. Пара граней
    переворачивается, только если она почти плоская (< max_dihedral) и
    минимальный угол растёт хотя бы на gain градусов.
    """
    V = m.vertices
    F = [list(f) for f in m.faces]
    changed = True
    while changed:
        changed = False
        edge_faces = {}
        for fi, f in enumerate(F):
            for k in range(3):
                e = tuple(sorted((f[k], f[(k + 1) % 3])))
                edge_faces.setdefault(e, []).append(fi)
        for (a, b), fs in edge_faces.items():
            if len(fs) != 2:
                continue
            f1, f2 = F[fs[0]], F[fs[1]]
            c = [v for v in f1 if v not in (a, b)][0]
            d = [v for v in f2 if v not in (a, b)][0]
            if tuple(sorted((c, d))) in edge_faces:
                continue
            # новое ребро не должно лечь в плоскость симметрии (y = 0)
            if abs(V[c, 1]) < 1e-6 and abs(V[d, 1]) < 1e-6:
                continue
            n1, n2 = _normal(V[f1]), _normal(V[f2])
            if np.degrees(np.arccos(np.clip(n1 @ n2, -1, 1))) > max_dihedral:
                continue
            before = min(_min_angle(V[f1]), _min_angle(V[f2]))
            # сохраняем ориентацию: в f1 порядок ... a -> b ... (или b -> a)
            i = f1.index(c)
            p, q = f1[(i + 1) % 3], f1[(i + 2) % 3]  # c, p, q — порядок обхода f1
            g1, g2 = [c, p, d], [d, q, c]
            after = min(_min_angle(V[g1]), _min_angle(V[g2]))
            if after < before + gain:
                continue
            # новые грани не должны «вывернуться»
            if _normal(V[g1]) @ n1 < 0.5 or _normal(V[g2]) @ n1 < 0.5:
                continue
            F[fs[0]], F[fs[1]] = g1, g2
            changed = True
            break
    return trimesh.Trimesh(V, np.array(F), process=False)


def fix_plane_chords(m):
    """Убирает внутренние рёбра половинки, лежащие в плоскости симметрии.

    Такое ребро (хорда через выемку профиля, например между крупом и хвостом)
    после зеркалирования оказалось бы общим для четырёх граней. Переворачиваем
    его — новая диагональ уходит с плоскости.
    """
    V = m.vertices
    F = [list(f) for f in m.faces]
    on_plane = np.abs(V[:, 1]) < 1e-6
    while True:
        edge_faces = {}
        for fi, f in enumerate(F):
            for k in range(3):
                edge_faces.setdefault(tuple(sorted((f[k], f[(k + 1) % 3]))), []).append(fi)
        bad = [(e, fs) for e, fs in edge_faces.items()
               if len(fs) == 2 and on_plane[e[0]] and on_plane[e[1]]]
        if not bad:
            break
        (a, b), fs = bad[0]
        f1, f2 = F[fs[0]], F[fs[1]]
        c = [v for v in f1 if v not in (a, b)][0]
        d = [v for v in f2 if v not in (a, b)][0]
        i = f1.index(c)
        p, q = f1[(i + 1) % 3], f1[(i + 2) % 3]
        F[fs[0]], F[fs[1]] = [c, p, d], [d, q, c]
    return trimesh.Trimesh(V, np.array(F), process=False)


def mirror_and_merge(half, eps=1e-3):
    v = half.vertices.copy()
    # вершины на краю половинки — строго на плоскость симметрии
    edges = half.edges_sorted
    uniq, counts = np.unique(edges, axis=0, return_counts=True)
    boundary = np.unique(uniq[counts == 1])
    v[boundary, 1] = 0.0
    f = half.faces
    vm = v * [1, -1, 1]
    fm = f[:, ::-1] + len(v)
    full = trimesh.Trimesh(np.vstack([v, vm]), np.vstack([f, fm]), process=False)
    full.merge_vertices(digits_vertex=4)
    full.update_faces(full.nondegenerate_faces())
    full.remove_unreferenced_vertices()
    full.fix_normals()
    return full


def split_long_edges(m, max_len):
    """Делит рёбра длиннее max_len пополам (самые длинные — первыми).

    Новая вершина лежит на середине ребра, обе соседние грани делятся надвое
    в своих плоскостях — форма модели не меняется, появляются лишь плоские
    (несгибаемые) линии, по которым развёртка может разрезать крупную грань.
    Работает на половинке модели: ребро на плоскости симметрии (одна грань)
    делится так же, новая вершина остаётся на плоскости.
    """
    V = [np.asarray(v, float) for v in m.vertices]
    F = [list(f) for f in m.faces]
    while True:
        edge_faces = {}
        for fi, f in enumerate(F):
            for k in range(3):
                edge_faces.setdefault(tuple(sorted((f[k], f[(k + 1) % 3]))), []).append(fi)
        a, b = max(edge_faces, key=lambda e: np.linalg.norm(V[e[0]] - V[e[1]]))
        if np.linalg.norm(V[a] - V[b]) <= max_len:
            break
        mid = (V[a] + V[b]) / 2
        if abs(V[a][1]) < 1e-9 and abs(V[b][1]) < 1e-9:
            mid[1] = 0.0
        V.append(mid)
        mi = len(V) - 1
        for fi in edge_faces[(a, b)]:
            f = F[fi]
            i = [k for k in range(3) if {f[k], f[(k + 1) % 3]} == {a, b}][0]
            p, q, r = f[i], f[(i + 1) % 3], f[(i + 2) % 3]  # ребро p->q, вершина r
            F[fi] = [p, mi, r]
            F.append([mi, q, r])
    return trimesh.Trimesh(np.array(V), np.array(F), process=False)


def build(target_half_faces=330, step=0.15, max_edge=None):
    """max_edge — предельная длина ребра в единицах модели (см до масштабирования)."""
    half = dense_half_mesh(step)
    low = decimate_half(half, target_half_faces)
    low = fix_plane_chords(improve_slivers(low))
    if max_edge:
        low = split_long_edges(low, max_edge)
    g = mirror_and_merge(low)
    assert g.is_watertight, "сетка не замкнута"
    return g


if __name__ == "__main__":
    import sys

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 330
    g = build(n)
    print("faces", len(g.faces), "verts", len(g.vertices), "watertight", g.is_watertight,
          "volume", round(g.volume, 1))
    print("bounds", g.bounds.round(1))
    print("холка, см:", round(withers_height(g), 1))
    g.export("out/goat.obj")
