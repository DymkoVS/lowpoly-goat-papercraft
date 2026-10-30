"""Раскрашенная коза: грани — краской (с белилами), рёбра — чёрной полосой заданной ширины.

Чёрная полоса строится геометрией: каждый треугольник делится на цветную середину
и чёрную кайму по 1/2 ширины ребра. Поэтому файлы выглядят одинаково в любом просмотрщике.

Запуск из корня проекта:
    .venv/bin/python goat/paint.py                          # v2, красная Decola + 10 % белил, ребро 2.5 мм
    .venv/bin/python goat/paint.py --obj out/v1/goat.obj --out out/v1/paint
    .venv/bin/python goat/paint.py --color "#33438a" --white 0 --edge 3 --no-video

Результат в --out:
    goat_painted.glb   3D для любого просмотрщика (Blender, Windows 3D Viewer, gltf-viewer.donmccurdy.com)
    goat_painted.usdz  3D для iPhone/iPad/Mac: открывается в Quick Look, кнопка AR ставит козу на пол
    goat_painted.png   картинка 3/4 спереди
    goat_painted.mp4   облёт по кругу, 8 с (нужен ffmpeg)
    goat_3d.html       страница с вращением, выбором красок, белил и ширины ребра (v1 и v2; three.js с CDN)
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import trimesh
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))

import render  # noqa: E402

DECOLA = [
    ('Белила титановые', '#efede6'), ('Лимонная', '#e8d24f'), ('Жёлтая средняя', '#e2b23f'),
    ('Охра золотистая', '#c39545'), ('Оранжевая', '#d9773a'), ('Красная светлая', '#cc4a3c'),
    ('Красная', '#b3342f'), ('Кармин', '#8a2934'), ('Малиновая', '#a3354f'), ('Розовая', '#de9aa0'),
    ('Сиреневая', '#a08cb2'), ('Фиолетовая', '#5d4578'), ('Ультрамарин', '#33438a'), ('Синяя', '#335f98'),
    ('Голубая', '#86b3d2'), ('Бирюзовая', '#409a98'), ('Изумрудная', '#24775b'), ('Зелёная светлая', '#8db44f'),
    ('Зелёная тёмная', '#335a3c'), ('Оливковая', '#7b783d'), ('Сиена жжёная', '#97492e'),
    ('Умбра жжёная', '#5d3c2c'), ('Серая', '#8b8d88'),
]
REDS = ['Охра золотистая', 'Оранжевая', 'Красная светлая', 'Красная', 'Кармин',
        'Малиновая', 'Розовая', 'Сиена жжёная', 'Умбра жжёная']

DECOLA_RED = "#b3342f"     # акрил Decola «Красная», оттенок примерный
TITAN_WHITE = "#efede6"    # Decola «Белила титановые»
WHITE_S = 12               # во сколько раз белила рассеивают сильнее цветного пигмента (на глаз)
EDGE_BLACK = (0.09, 0.09, 0.085)


def srgb_to_lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(np.asarray(c, float), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def tint(hex_color, white):
    """Краска + доля белил (0..1): Кубелка–Мунк с двумя константами, по каналам. Возвращает sRGB 0..1."""
    R, W = srgb_to_lin(hex_rgb(hex_color)), srgb_to_lin(hex_rgb(TITAN_WHITE))
    if white <= 0:
        return hex_rgb(hex_color)
    ks = lambda r: (1 - np.clip(r, 1e-3, 0.999)) ** 2 / (2 * np.clip(r, 1e-3, 0.999))
    K = ((1 - white) * ks(R) + white * WHITE_S * ks(W)) / ((1 - white) + white * WHITE_S)
    return lin_to_srgb(1 + K - np.sqrt(K * K + 2 * K))


def panels(mesh):
    """Общие плоские рёбра объединяют треугольники в панели."""
    parent = list(range(len(mesh.faces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    flat = set()
    for (a, b), edge in zip(mesh.face_adjacency, mesh.face_adjacency_edges):
        if abs(mesh.face_normals[a] @ mesh.face_normals[b]) > 0.99995:
            flat.add(tuple(sorted(edge)))
            parent[find(int(a))] = find(int(b))
    ids = {}
    panel = []
    for i in range(len(parent)):
        root = find(i)
        panel.append(ids.setdefault(root, len(ids)))
    adj = [set() for _ in ids]
    for a, b in mesh.face_adjacency:
        a, b = panel[a], panel[b]
        if a != b:
            adj[a].add(b)
            adj[b].add(a)
    return np.array(panel), adj, flat


def color_panels(adj, n_colors, seed):
    """Балансируем число панелей, затем уменьшаем конфликты обменом цветов."""
    rng = random.Random(seed)
    n = len(adj)
    best, best_bad = None, float("inf")
    for attempt in range(2 if n_colors < 4 else 40):
        # Квоты отличаются не больше чем на одну панель, в том числе при двух красках.
        colors = [i % n_colors for i in range(n)]
        rng.shuffle(colors)
        edges = [(a, b) for a in range(n) for b in sorted(adj[a]) if a < b]
        bad = sum(colors[a] == colors[b] for a, b in edges)
        for step in range(20):
            changed = False
            order = list(range(n))
            rng.shuffle(order)
            for a in order:
                if not any(colors[a] == colors[b] for b in adj[a]):
                    continue
                candidates = list(range(n))
                rng.shuffle(candidates)
                for b in candidates:
                    ca, cb = colors[a], colors[b]
                    if ca == cb:
                        continue
                    affected = {(min(v, w), max(v, w)) for v in (a, b) for w in adj[v]}
                    before = sum(colors[v] == colors[w] for v, w in affected)
                    colors[a], colors[b] = cb, ca
                    after = sum(colors[v] == colors[w] for v, w in affected)
                    if after < before:
                        bad += after - before
                        changed = True
                        break
                    colors[a], colors[b] = ca, cb
            if not bad or not changed:
                break
        if bad < best_bad:
            best, best_bad = colors[:], bad
        if not bad or n_colors == 1:
            break
    return np.array(best), best_bad


def paint_pool(args):
    """Пользовательский список имеет приоритет над готовой палитрой."""
    if args.paints is not None:
        names = list(dict.fromkeys(x.strip() for x in args.paints.split(",") if x.strip()))
        known = dict(DECOLA)
        if not names or any(name not in known for name in names):
            raise ValueError("Неизвестная или пустая краска. Допустимые: " + ", ".join(known))
        return [(name, known[name]) for name in names]
    if args.palette == "decola":
        return [(name, color) for name, color in DECOLA if name not in ("Белила титановые", "Серая")]
    if args.palette == "reds":
        return [(name, dict(DECOLA)[name]) for name in REDS]
    return [("Красная" if args.color == DECOLA_RED else args.color, args.color)]


def bake(mesh, half_w, flat=None):
    """Делит треугольники на цветную середину и чёрную кайму.

    Плоские рёбра (раздел больших треугольников в v2) не красятся.
    Возвращает вершины, цветные и чёрные грани, длину рёбер,
    число вырожденных граней и исходный треугольник каждой цветной грани.
    """
    V, F = mesh.vertices, mesh.faces
    if flat is None:
        _, _, flat = panels(mesh)
    ink = sum(np.linalg.norm(V[e[0]] - V[e[1]]) for e in mesh.face_adjacency_edges
              if tuple(sorted(e)) not in flat)
    out_v, col_f, blk_f, degenerate = [], [], [], 0
    col_source = []
    for face_id, tri in enumerate(F):
        P = V[tri]
        # h[k] — высота на ребро напротив вершины k; d[k] — отступ от этого ребра
        h, d = np.zeros(3), np.zeros(3)
        for k in range(3):
            a, b = P[(k + 1) % 3], P[(k + 2) % 3]
            h[k] = np.linalg.norm(np.cross(P[k] - a, b - a)) / np.linalg.norm(b - a)
            e = tuple(sorted((tri[(k + 1) % 3], tri[(k + 2) % 3])))
            d[k] = 0.0 if e in flat else half_w
        if 1 - (d / h).sum() <= 1e-6:      # грань целиком уходит в чёрное
            base = len(out_v)
            out_v.extend(P)
            blk_f.append([base, base + 1, base + 2])
            degenerate += 1
            continue
        # внутренняя вершина k: барицентрики b_j = d_j / h_j для двух соседних рёбер
        inner = []
        for k in range(3):
            b = d / h
            b[k] = 1 - b[(k + 1) % 3] - b[(k + 2) % 3]
            inner.append(b @ P)
        base = len(out_v)
        out_v.extend(P)
        out_v.extend(inner)
        col_f.append([base + 3, base + 4, base + 5])
        col_source.append(face_id)
        for k in range(3):                 # кайма вдоль ребра напротив вершины k
            if d[k] == 0:
                continue
            i, j = (k + 1) % 3, (k + 2) % 3
            blk_f.append([base + i, base + j, base + 3 + j])
            blk_f.append([base + i, base + 3 + j, base + 3 + i])
    return (np.array(out_v), np.array(col_f, dtype=int).reshape(-1, 3),
            np.array(blk_f, dtype=int).reshape(-1, 3), ink, degenerate,
            np.array(col_source, dtype=int))


def to_y_up_m(v):
    """см, Z вверх → метры, Y вверх (glTF/USD)."""
    return np.c_[v[:, 0], v[:, 2], -v[:, 1]] / 100.0


def export_glb(path, V, groups):
    Vy = to_y_up_m(V)
    scene = trimesh.Scene()
    for name, faces, c in groups:
        m = trimesh.Trimesh(Vy, faces, process=False)
        m.remove_unreferenced_vertices()
        m.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
            name=name, baseColorFactor=[*np.round(np.asarray(c) * 255).astype(int), 255],
            metallicFactor=0.0, roughnessFactor=1.0, doubleSided=True))
        scene.add_geometry(m, node_name=name)
    scene.export(path)


def export_usdz(path, V, groups):
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdUtils, Vt

    tmp = tempfile.mkdtemp()
    usdc = os.path.join(tmp, "goat.usdc")
    stage = Usd.Stage.CreateNew(usdc)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, "/Goat")
    stage.SetDefaultPrim(root.GetPrim())
    Vy = to_y_up_m(V)
    for name, faces, c in groups:
        used = np.unique(faces)
        remap = np.full(len(Vy), -1)
        remap[used] = np.arange(len(used))
        mesh = UsdGeom.Mesh.Define(stage, f"/Goat/{name}")
        mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float, p)) for p in Vy[used]]))
        mesh.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(faces)))
        mesh.CreateFaceVertexIndicesAttr(Vt.IntArray([int(i) for i in remap[faces].ravel()]))
        mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        mesh.CreateDoubleSidedAttr(True)
        mat = UsdShade.Material.Define(stage, f"/Goat/{name}_mat")
        sh = UsdShade.Shader.Define(stage, f"/Goat/{name}_mat/surface")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*map(float, c)))
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
        sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(mat)
    stage.GetRootLayer().Save()
    UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(usdc), path)
    shutil.rmtree(tmp)


def export_html(path, objs=(("v1", "out/v1/goat.obj"), ("v2", "out/v2/goat.obj"))):
    """Интерактивная страница: шаблон goat/viewer.html + вершины и грани обеих моделей."""
    data = {}
    for key, obj in objs:
        m = trimesh.load(obj, process=False)
        data[key] = {"v": np.round(m.vertices, 3).ravel().tolist(), "f": m.faces.ravel().tolist()}
    tpl = open(os.path.join(os.path.dirname(__file__), "viewer.html"), encoding="utf-8").read()
    with open(path, "w", encoding="utf-8") as f:
        f.write(tpl.replace("__DATA__", json.dumps(data, separators=(",", ":"))))


def frame(V, faces, colors, angle, size, ss=2, bg=(0.96, 0.96, 0.95)):
    """Кадр: модель повёрнута вокруг вертикали на angle°, камера и свет неподвижны."""
    a = np.radians(angle)
    Rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    c = (V.min(0) + V.max(0)) / 2
    m = trimesh.Trimesh((V - c) @ Rz.T, faces, process=False)
    img, _ = render.rasterize(m, 12, -60, (size * ss, size * ss), colors, pad=0.02,
                              edges=False, bg=bg)
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    return im.resize((size, size), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--obj", default="out/v2/goat.obj", help="модель (см, Z вверх)")
    ap.add_argument("--out", default="out/v2/paint")
    ap.add_argument("--color", default=DECOLA_RED, help="краска граней, hex")
    ap.add_argument("--palette", choices=("single", "decola", "reds"), default="single")
    ap.add_argument("--paints", help="названия красок через запятую; приоритет над --palette")
    ap.add_argument("--seed", type=int, default=0, help="seed воспроизводимой раскраски")
    ap.add_argument("--white", type=float, default=10, help="белил в краске, %%")
    ap.add_argument("--edge", type=float, default=2.5, help="ширина чёрного ребра, мм")
    ap.add_argument("--size", type=int, default=1080, help="сторона картинки и видео, px")
    ap.add_argument("--seconds", type=float, default=8)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--no-video", action="store_true")
    args = ap.parse_args()

    try:
        pool = paint_pool(args)
    except ValueError as exc:
        ap.error(str(exc))
    os.makedirs(args.out, exist_ok=True)
    mesh = trimesh.load(args.obj, process=False)
    mesh.merge_vertices()
    panel, adj, flat = panels(mesh)
    assigned, conflicts = color_panels(adj, len(pool), args.seed)
    V, col_f, blk_f, ink, bad, source = bake(mesh, args.edge / 10 / 2, flat)
    rgb = np.array([tint(color, args.white / 100) for _, color in pool])
    print(f"панелей {len(adj)}; ребро {args.edge:g} мм; чёрных рёбер {ink / 100:.1f} м; "
          f"граней целиком в чёрном: {bad}")
    print("Список покупок (количество панелей, не объём краски):")
    for i, (name, _) in enumerate(pool):
        hexc = "#" + "".join(f"{round(x * 255):02x}" for x in rgb[i])
        print(f"  {name}: {np.count_nonzero(assigned == i)} панелей; с белилами {hexc}")
    print(f"Соседних пар одного цвета: {conflicts}")
    face_colors = assigned[panel[source]]
    groups = [(f"paint_{i}", col_f[face_colors == i], color)
              for i, color in enumerate(rgb) if np.any(face_colors == i)]
    if len(blk_f):
        groups.append(("edges", blk_f, EDGE_BLACK))
    export_glb(os.path.join(args.out, "goat_painted.glb"), V, groups)
    export_usdz(os.path.join(args.out, "goat_painted.usdz"), V, groups)
    export_html(os.path.join(args.out, "goat_3d.html"))

    faces = np.vstack([col_f, blk_f])
    colors = np.vstack([rgb[face_colors], np.tile(EDGE_BLACK, (len(blk_f), 1))])
    frame(V, faces, colors, 0, args.size).save(os.path.join(args.out, "goat_painted.png"))
    if args.no_video or not shutil.which("ffmpeg"):
        print("видео пропущено")
        return
    n = int(args.seconds * args.fps)
    tmp = tempfile.mkdtemp()
    for i in range(n):
        frame(V, faces, colors, 360 * i / n, args.size).save(os.path.join(tmp, f"f{i:04d}.png"))
        if i % 30 == 0:
            print(f"  кадр {i}/{n}", flush=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(args.fps),
                    "-i", os.path.join(tmp, "f%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "20", "-movflags", "+faststart", os.path.join(args.out, "goat_painted.mp4")],
                   check=True)
    shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
