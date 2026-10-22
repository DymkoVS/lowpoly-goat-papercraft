"""Отладочная картинка: все детали развёртки в сетке (красное — ребро без клапана)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot_islands(u, path):
    n = len(u.islands)
    cols = 6
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 4 * rows), squeeze=False)
    for ax in axes.ravel():
        ax.set_axis_off()
    for ii, (isl, ax) in enumerate(zip(u.islands, axes.ravel())):
        for f, P in isl.faces.items():
            ax.fill(*P.T, color="#eee", ec="none")
            Ff = list(u.F[f])
            for k in range(3):
                e = tuple(sorted((int(Ff[k]), int(Ff[(k + 1) % 3]))))
                a, b = P[k], P[(k + 1) % 3]
                if u.edge_kind[e] == "fold":
                    ax.plot([a[0], b[0]], [a[1], b[1]], "g-." if u.convex[e] else "b--", lw=0.6)
                else:
                    red = u.tab_side[e] is None
                    ax.plot([a[0], b[0]], [a[1], b[1]], "r" if red else "k", lw=1.5 if red else 0.8)
        for _, tp, _, _ in isl.tabs:
            ax.fill(*tp.exterior.xy, color="#bbb", ec="k", lw=0.4)
        ax.set_aspect("equal")
        ax.set_title(f"{ii}: {isl.region} ({len(isl.faces)})")
    fig.tight_layout()
    fig.savefig(path, dpi=70)
    plt.close(fig)
