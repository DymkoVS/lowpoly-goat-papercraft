"""Рендер low-poly модели в PNG: свой растеризатор с z-буфером.

Каждый пиксель знает номер грани, поэтому контуры граней рисуются честно
(без «просвечивания» задних граней, как у matplotlib 3D).
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

VIEWS = [("сбоку", 0, -90), ("3/4 спереди", 20, -35), ("спереди", 5, 0),
         ("сверху", 89, -90), ("3/4 сзади", 25, -145), ("снизу", -50, -60)]


def view_matrix(elev, azim):
    """Ортографическая камера: возвращает 3x3 (строки — экранные x, y и глубина)."""
    e, a = np.radians(elev), np.radians(azim)
    # направление на камеру
    d = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    up = np.array([0, 0, 1.0]) if abs(elev) < 85 else np.array([1.0, 0, 0])
    right = np.cross(up, d)
    right /= np.linalg.norm(right)
    up2 = np.cross(d, right)
    return np.stack([right, up2, d])


def rasterize(mesh, elev, azim, size=700, colors=None, pad=0.05, headlight=False, tight=False,
              edges=True, bg=(1.0, 1.0, 1.0)):
    """Возвращает картинку и (px, py, s, c) — экранные координаты вершин, масштаб и центр.

    size — число или (ширина, высота); tight — кадрировать по проекции модели.
    headlight — свет от камеры (все видимые грани светлые).
    edges — затемнять границы граней (для раскрашенной модели рёбра уже есть в геометрии).
    """
    R = view_matrix(elev, azim)
    v = mesh.vertices @ R.T
    W, H = (size, size) if np.isscalar(size) else size
    if tight:
        lo2, hi2 = v[:, :2].min(0), v[:, :2].max(0)
        c = np.r_[(lo2 + hi2) / 2, 0]
        s = min(W / ((hi2[0] - lo2[0]) * (1 + pad)), H / ((hi2[1] - lo2[1]) * (1 + pad)))
    else:
        lo, hi = mesh.bounds
        c = ((lo + hi) / 2) @ R.T
        s = min(W, H) / (np.linalg.norm(hi - lo) * (1 + pad))
    px = (v[:, 0] - c[0]) * s + W / 2
    py = H / 2 - (v[:, 1] - c[1]) * s
    pz = v[:, 2]
    zbuf = np.full((H, W), -np.inf)
    fid = np.full((H, W), -1)
    for i, (a, b, cc) in enumerate(mesh.faces):
        x = np.array([px[a], px[b], px[cc]])
        y = np.array([py[a], py[b], py[cc]])
        z = np.array([pz[a], pz[b], pz[cc]])
        x0, x1 = int(max(np.floor(x.min()), 0)), int(min(np.ceil(x.max()), W - 1))
        y0, y1 = int(max(np.floor(y.min()), 0)), int(min(np.ceil(y.max()), H - 1))
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        den = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if abs(den) < 1e-12:
            continue
        w0 = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / den
        w1 = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        depth = w0 * z[0] + w1 * z[1] + w2 * z[2]
        sub_z = zbuf[y0:y1 + 1, x0:x1 + 1]
        upd = inside & (depth > sub_z)
        sub_z[upd] = depth[upd]
        fid[y0:y1 + 1, x0:x1 + 1][upd] = i

    n = mesh.face_normals
    if headlight:
        k = 0.55 + 0.45 * np.abs(n @ R[2])
    else:
        light = np.array([0.35, -0.55, 0.75])
        light /= np.linalg.norm(light)
        k = 0.38 + 0.62 * np.clip(n @ light, 0, 1)
    base = np.ones((len(mesh.faces), 3)) * 0.95 if colors is None else np.asarray(colors)[:, :3]
    fc = np.clip(base * k[:, None], 0, 1)
    img = np.ones((H, W, 3)) * np.asarray(bg)
    m = fid >= 0
    img[m] = fc[fid[m]]
    if edges:
        edge = np.zeros_like(m)
        edge[:, 1:] |= fid[:, 1:] != fid[:, :-1]
        edge[1:, :] |= fid[1:, :] != fid[:-1, :]
        img[edge] = img[edge] * 0.35
    return img, (px, py, s, c)


def render(mesh, path, colors=None, views=VIEWS, size=700, labels=None):
    n = len(views)
    cols = min(3, n)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 5 * rows), dpi=110, squeeze=False)
    for ax in axes.ravel():
        ax.set_axis_off()
    for (title, el, az), ax in zip(views, axes.ravel()):
        img, (px, py, s, _) = rasterize(mesh, el, az, size, colors)
        ax.imshow(img)
        ax.set_title(title)
        if labels:
            R = view_matrix(el, az)
            lo, hi = mesh.bounds
            c = ((lo + hi) / 2) @ R.T
            for txt, pos in labels:
                q = np.asarray(pos) @ R.T
                ax.text((q[0] - c[0]) * s + size / 2, size / 2 - (q[1] - c[1]) * s, txt,
                        fontsize=7, ha="center", va="center")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


if __name__ == "__main__":
    import sys

    import trimesh

    m = trimesh.load(sys.argv[1], process=False)
    render(m, sys.argv[2])
