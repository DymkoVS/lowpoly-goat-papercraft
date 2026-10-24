"""Low-poly goat papercraft: model -> unfolding -> A4 layout -> checked PDF (RU/EN).

Run from the project root:
    python goat/build.py --preset v1                 # small goat, 30 cm at withers
    python goat/build.py --preset v2                 # large goat, 80 cm to horn tips (built and checked)
    python goat/build.py --total-height 60 --faces 400 --max-edge 150 --tab 10 --version my60

A PDF is written only if every geometric check passes (see validate()).
"""
import argparse
import collections
import json
import os
import sys

import matplotlib
import numpy as np
import shapely
from shapely.geometry import Polygon

sys.path.insert(0, os.path.dirname(__file__))

import i18n  # noqa: E402
import intro  # noqa: E402
import layout  # noqa: E402
import model  # noqa: E402
import pdf  # noqa: E402
import render  # noqa: E402
from i18n import T, piece_name  # noqa: E402
from unfold import Unfolder, tri_overlap  # noqa: E402

# порядок сборки: голова, шея, тело, хвост, ноги
REGION_ORDER = ["head", "horn", "ear", "neck", "body_f", "body_r", "tail", "fleg", "hleg"]
GROUPS = {"head": "H", "ear": "H", "horn": "H", "neck": "N", "body_f": "N", "body_r": "B", "tail": "B"}

MATERIAL_CARD = {
    "ru": "бумага 160 г/м² или 80 г/м² на тонком картоне",
    "en": "160 g/m² card, or 80 g/m² paper on thin cardboard",
}
MATERIAL_BOARD = {
    "ru": "бумага 80–160 г/м², наклеенная на картон",
    "en": "80–160 g/m² paper glued onto cardboard",
}

# настройки опубликованных выкроек (v2 собрана и проверена)
PRESETS = {
    "v1": dict(height=30.0, total_height=None, faces=320, max_edge=None, tab=7.0, version="v1",
               material=MATERIAL_CARD),
    "v2": dict(height=None, total_height=80.0, faces=400, max_edge=150.0, tab=10.0, version="v2",
               material=MATERIAL_BOARD),
}


def order_and_name(u):
    """Упорядочить детали (левые, затем их зеркальные пары): номер + сторона L/R."""
    n = len(u.islands) // 2
    left = list(range(n))

    def key(i):
        isl = u.islands[i]
        return (REGION_ORDER.index(isl.region) if isl.region in REGION_ORDER else 99, -len(isl.faces))

    left.sort(key=key)
    new = [u.islands[i] for i in left] + [u.islands[i + n] for i in left]
    for k, isl in enumerate(new):
        isl.number = k % n + 1
        isl.side = "L" if k < n else "R"
        isl.name = f"{isl.number}{isl.side}"
    u.islands = new
    u.compact()


def validate(u):
    """Все проверки геометрии. Возвращает список проблем (пустой — выкройка корректна).

    1. Длины рёбер на развёртке = длинам в 3D-модели.
    2. Все грани лежат лицевой стороной вверх (печать — наружная поверхность).
    3. Внутри детали грани не налезают друг на друга; клапаны не налезают на детали.
    4. Каждый номер разреза встречается ровно на двух гранях, у каждого разреза есть клапан.
    5. Правые детали — зеркальные копии левых.
    """
    problems = []
    max_err = 0.0
    for isl in u.islands:
        for f, P in isl.faces.items():
            V = u.V[u.F[f]]
            for k in range(3):
                d2 = np.linalg.norm(P[k] - P[(k + 1) % 3])
                d3 = np.linalg.norm(V[k] - V[(k + 1) % 3])
                max_err = max(max_err, abs(d2 - d3))
            a, b = P[1] - P[0], P[2] - P[0]
            if a[0] * b[1] - a[1] * b[0] <= 0:
                problems.append(f"{isl.name}: face {f} is upside down")
    if max_err > 0.01:
        problems.append(f"edge length error {max_err:.3f} mm")
    for isl in u.islands:
        items = list(isl.faces.items())
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if tri_overlap(items[i][1], items[j][1]):
                    inter = shapely.intersection(Polygon(items[i][1]), Polygon(items[j][1]), grid_size=1e-4).area
                    problems.append(f"{isl.name}: faces {items[i][0]} and {items[j][0]} overlap ({inter:.1f} mm²)")
        for _, tp, _, _ in isl.tabs:
            if shapely.intersection(tp.buffer(-0.3), isl.poly, grid_size=1e-4).area > 0.5:
                problems.append(f"{isl.name}: a glue tab overlaps the piece")
    count = collections.Counter()
    for isl in u.islands:
        for f, P in isl.faces.items():
            Ff = [int(v) for v in u.F[f]]
            for k in range(3):
                e = tuple(sorted((Ff[k], Ff[(k + 1) % 3])))
                if u.edge_kind[e] == "cut":
                    count[u.cut_ids[e]] += 1
    if set(count.values()) - {2}:
        problems.append("some edge numbers do not appear exactly twice")
    notab = [e for e, s in u.tab_side.items() if s is None]
    if notab:
        problems.append(f"{len(notab)} edges without a glue tab")
    n = len(u.islands) // 2
    for i in range(n):
        L, R = u.islands[i], u.islands[i + n]
        aL = sorted(round(Polygon(P).area, 1) for P in L.faces.values())
        aR = sorted(round(Polygon(P).area, 1) for P in R.faces.values())
        if aL != aR:
            problems.append(f"{L.name}/{R.name}: right piece is not a mirror of the left one")
    return problems


def warnings(mesh, u, withers_cm):
    """Предупреждения о размерах, при которых клеить будет неудобно (PDF всё равно создаётся)."""
    out = []
    edges = mesh.edges_unique_length * 10  # мм
    if edges.min() < 6:
        out.append(f"shortest edge is {edges.min():.1f} mm — horn and ear tips will be fiddly to fold")
    if withers_cm < 20:
        out.append("goat is smaller than 20 cm at the withers — small parts may be hard to assemble")
    if withers_cm > 45:
        out.append("large goat: glue the printouts onto cardboard and add bulkheads inside")
    sizes = [len(i.faces) for i in u.islands]
    if sizes.count(1) > 6:
        out.append(f"{sizes.count(1)} single-triangle pieces")
    return out


def belly_seam(mesh, u):
    """Номера рёбер шва по животу (средняя линия внизу) — последний шов при сборке."""
    V = u.V
    top = V[:, 2].max()
    nums = []
    for e, kind in u.edge_kind.items():
        if kind != "cut":
            continue
        a, b = V[e[0]], V[e[1]]
        if abs(a[1]) < 1e-6 and abs(b[1]) < 1e-6 and max(a[2], b[2]) < 0.45 * top:
            nums.append((a[0] + b[0], u.cut_ids[e]))
    return [n for _, n in sorted(nums)]


def assembly_render(mesh, u, path):
    cmap = matplotlib.colormaps["tab20"]
    colors = np.zeros((len(mesh.faces), 4))
    for isl in u.islands:
        col = np.array(cmap((isl.number - 1) % 20))
        col[:3] = 0.45 + 0.55 * col[:3]  # светлее, чтобы читались подписи
        for f in isl.faces:
            colors[f] = col
    cen = mesh.triangles_center
    area = mesh.area_faces
    off = 0.06 * np.ptp(mesh.bounds[:, 1])  # вынос подписи наружу

    def labels(side):
        out = []
        for isl in u.islands:
            if isl.side == side:
                fs = list(isl.faces)
                p = (cen[fs] * area[fs, None]).sum(0) / area[fs].sum()
                p = p + np.array([0, off if side == "L" else -off, 0])
                out.append((piece_name(isl), p))
        return out

    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(11, 14), dpi=130)
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.75])
    panels = [(gs[0, :], T("map_left"), 0, 90, "L", (1400, 1150)),
              (gs[1, :], T("map_right"), 0, -90, "R", (1400, 1150)),
              (gs[2, 0], T("map_front"), 30, -20, None, (700, 700)),
              (gs[2, 1], T("map_bottom"), -70, 60, None, (700, 700))]
    for spec, title, el, az, side, size in panels:
        ax = fig.add_subplot(spec)
        img, (px, py, s, cc) = render.rasterize(mesh, el, az, size, colors, headlight=True, tight=True)
        ax.imshow(img)
        ax.set_title(title, fontsize=13)
        ax.set_axis_off()
        if side:
            R = render.view_matrix(el, az)
            W, H = size
            for txt, pos in labels(side):
                q = np.asarray(pos) @ R.T
                ax.text((q[0] - cc[0]) * s + W / 2, H / 2 - (q[1] - cc[1]) * s, txt, fontsize=10,
                        ha="center", va="center", weight="bold",
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Low-poly goat papercraft pattern generator")
    ap.add_argument("--preset", choices=sorted(PRESETS), help="published version: v1 (30 cm) or v2 (80 cm)")
    ap.add_argument("--height", type=float, help="height at withers, cm (default 30)")
    ap.add_argument("--total-height", type=float, help="height to horn tips, cm (instead of --height)")
    ap.add_argument("--faces", type=int, help="number of faces (default 320)")
    ap.add_argument("--max-edge", type=float, help="max edge length on paper, mm; longer edges are split")
    ap.add_argument("--tab", type=float, help="glue tab height, mm (default 7)")
    ap.add_argument("--version", help="version label in the PDF title and file name")
    ap.add_argument("--lang", default="ru,en", help="PDF languages, comma separated: ru,en")
    ap.add_argument("--tries", type=int, default=200, help="unfolding attempts per body region")
    ap.add_argument("--max-w", type=float, default=160.0, help="max piece width without tabs, mm")
    ap.add_argument("--max-h", type=float, default=200.0, help="max piece height without tabs, mm")
    ap.add_argument("--pack-tries", type=int, default=16, help="sheet packing attempts")
    ap.add_argument("--out", help="output folder (default out/<version>)")
    args = ap.parse_args()

    cfg = dict(PRESETS.get(args.preset) or dict(height=30.0, total_height=None, faces=320, max_edge=None,
                                                 tab=7.0, version="custom", material=MATERIAL_CARD))
    for key in ("height", "total_height", "faces", "max_edge", "tab", "version"):
        v = getattr(args, key)
        if v is not None:
            cfg[key] = v
    if args.total_height is not None:
        cfg["height"] = None
    elif args.height is not None:
        cfg["total_height"] = None
    langs = [x.strip() for x in args.lang.split(",") if x.strip()]
    for lang in langs:
        i18n.set_lang(lang)  # проверка, что язык известен
    out = args.out or os.path.join("out", cfg["version"])
    os.makedirs(out, exist_ok=True)

    print("1/5 model…")
    mesh = model.build(cfg["faces"] // 2)
    if cfg["total_height"]:
        k = cfg["total_height"] / mesh.bounds[1, 2]
    else:
        k = cfg["height"] / model.withers_height(mesh)
    if cfg["max_edge"]:
        # дробление делаем на модели в исходных единицах (см), потом масштабируем
        mesh = model.build(cfg["faces"] // 2, max_edge=cfg["max_edge"] / 10 / k)
    mesh.apply_scale(k)
    withers = model.withers_height(mesh)
    print(f"    {len(mesh.faces)} faces, {withers:.1f} cm at withers, "
          f"size {np.ptp(mesh.bounds, axis=0).round(1)} cm")
    mesh.export(os.path.join(out, "goat.obj"))
    regions = model.face_regions(mesh, scale=k)

    print("2/5 unfolding…")
    u = Unfolder(mesh, regions=regions, groups=GROUPS, max_w=args.max_w, max_h=args.max_h, tab_h=cfg["tab"])
    u.unfold_symmetric(tries=args.tries)
    order_and_name(u)
    u.classify_edges()
    u.make_tabs()
    sizes = [len(i.faces) for i in u.islands]
    n_cut = sum(1 for v in u.edge_kind.values() if v == "cut")
    print(f"    {len(sizes)} pieces ({len(sizes) // 2} L/R pairs), {n_cut} glued edges")

    print("3/5 checks…")
    problems = validate(u)
    if problems:
        for p in problems:
            print("    ERROR: " + p)
        print("    The pattern failed the checks, no PDF written. Try other --faces / --max-edge values.")
        sys.exit(1)
    print("    all geometric checks passed")
    for w in warnings(mesh, u, withers):
        print("    warning: " + w)

    print("4/5 sheet layout…")
    try:
        pages = layout.pack_best(u, u.islands, tries=args.pack_tries)
    except RuntimeError as exc:
        print(f"    ERROR: {exc}. Use a larger --faces or --max-edge 150.")
        sys.exit(1)
    for i, page in enumerate(pages, 1):
        for isl in page.items:
            isl.sheet = i
    print(f"    {len(pages)} A4 sheets")

    print("5/5 PDF…")
    stats = {
        "version": cfg["version"],
        "faces": int(len(mesh.faces)),
        "withers_cm": round(float(withers), 1),
        "size_cm": [round(float(x), 1) for x in np.ptp(mesh.bounds, axis=0)],
        "pieces": len(sizes),
        "cuts": n_cut,
        "pages": len(pages),
        "tab_mm": cfg["tab"],
        "material": cfg["material"],
        "belly_seam": belly_seam(mesh, u),
        "params": {k2: cfg[k2] for k2 in ("height", "total_height", "faces", "max_edge", "tab")},
    }
    render.render(mesh, os.path.join(out, "goat_views.png"))
    for lang in langs:
        i18n.set_lang(lang)
        assembly_render(mesh, u, os.path.join(out, f"assembly_map_{lang}.png"))
        title = T("short_title", version=cfg["version"])
        path = os.path.join(out, f"goat_pattern_{cfg['version']}_{lang}.pdf")
        pdf.write_pattern(path, u, pages, title, intro=lambda c, lang=lang: intro.draw(c, stats, u, out, lang))
        print("    " + path)
    with open(os.path.join(out, "stats.json"), "w") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
