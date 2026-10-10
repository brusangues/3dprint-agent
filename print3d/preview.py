"""Preview 3D da malha em PNG (requer matplotlib e numpy).

Rasterizador próprio com z-buffer por pixel. Não usa mplot3d porque ele
ordena as faces por distância média ao centro, o que produz raios-X: um
furo passante atravessa a peça e o fundo aparece por cima da parede.

Com z-buffer por pixel a oclusão é resolvida triângulo a triângulo, que
é o único jeito de uma peça furada aparecer furada. O custo é cerca de
1M de operações em Python puro por painel, o que leva menos de um
segundo numa peça de poucas centenas de faces.
"""

from __future__ import annotations

import math
from pathlib import Path

from .mesh import Mesh, normal_unit

VIEWS = {
    # nome: (elevação, azimute)
    "iso": (26, -58),
    "iso2": (20, 122),
    "iso3": (32, -145),
    "top": (89.9, -90),
    "bottom": (-89.9, -90),
    "front": (8, -90),
    "back": (8, 90),
    "left": (8, 0),
    "right": (8, 180),
}


def _matriz(elev: float, azim: float) -> tuple[float, ...]:
    """Matriz 3x3 (linha-major) que gira a peça para a câmera.

    Convenção: z da peça é o "cima" do mundo, x a direita, y o fundo.
    A câmera olha de cima (elevação) e gira em torno do z (azimute).
    """
    e, a = math.radians(elev), math.radians(azim)
    ce, se = math.cos(e), math.sin(e)
    ca, sa = math.cos(a), math.sin(a)
    m1 = (1.0, 0.0, 0.0, 0.0, ce, se, 0.0, -se, ce)    # elevação (em torno de x)
    m2 = (ca, -sa, 0.0, sa, ca, 0.0, 0.0, 0.0, 1.0)    # azimute (em torno de z)
    # a peça gira primeiro em azimute e depois em elevação: M = m1 * m2
    return _mul(m1, m2)


def _mul(a, b):
    return tuple(
        sum(a[r * 3 + k] * b[k * 3 + c] for k in range(3)) for r in range(3) for c in range(3)
    )


def _aplicar(m, p):
    x, y, z = p
    return (
        m[0] * x + m[1] * y + m[2] * z,
        m[3] * x + m[4] * y + m[5] * z,
        m[6] * x + m[7] * y + m[8] * z,
    )


def render_png(
    mesh: Mesh,
    path: str | Path,
    views: str = "iso",
    title: str | None = None,
    res: int = 560,
) -> Path:
    """Desenha a malha em PNG. Views separadas por '+'.

    Rasteriza com z-buffer real, então furos passantes e cavidades
    aparecem corretamente.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "preview precisa de matplotlib e numpy: pip install matplotlib numpy"
        ) from exc

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    chaves = [k.strip() for k in views.split("+") if k.strip()]
    specs = [(k, VIEWS[k]) for k in chaves if k in VIEWS] or [("iso", VIEWS["iso"])]

    m = mesh.copy().center_on_origin()
    lo, hi = m.bbox_min(), m.bbox_max()
    diag = math.sqrt(sum((hi[i] - lo[i]) ** 2 for i in range(3))) or 1.0
    centro = m.centroid_bbox()

    n = len(specs)
    fig, axes = plt.subplots(1, n, figsize=(4.1 * n, 4.1))
    if n == 1:
        axes = [axes]

    for ax, (rotulo, (elev, azim)) in zip(axes, specs):
        M = _matriz(elev, azim)
        proj = [
            _aplicar(M, (v[0] - centro[0], v[1] - centro[1], v[2] - centro[2]))
            for v in m.vertices
        ]
        xs = [p[0] for p in proj]
        ys = [p[1] for p in proj]
        alcance = max(max(xs) - min(xs), max(ys) - min(ys)) or diag
        escala = 0.92 / alcance
        cx = (max(xs) + min(xs)) / 2.0
        cy = (max(ys) + min(ys)) / 2.0

        tris = []
        for a, b, c in m.faces:
            # a normal gira junto com a peça, senão o sombreamento mente
            nr = _aplicar(M, normal_unit(m.vertices[a], m.vertices[b], m.vertices[c]))
            facing = 0.38 + 0.62 * abs(nr[2]) + 0.16 * max(0.0, -nr[1])
            shade = min(1.0, max(0.15, facing))
            pts = []
            for idx in (a, b, c):
                q = proj[idx]
                pts.append(((q[0] - cx) * escala, (q[1] - cy) * escala, q[2]))
            tris.append((pts, shade))

        img = _raster(tris, res, np)
        ax.imshow(
            img,
            origin="upper",
            extent=(-1.02, 1.02, -1.02, 1.02),
            interpolation="bilinear",
        )
        ax.set_xlim(-1.05, 1.05)
        ax.set_ylim(-1.05, 1.05)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(rotulo, fontsize=10, color="#333")

    fig.suptitle(
        title or f"{mesh.name}   {mesh.n_vertices} vertices / {mesh.n_faces} faces",
        fontsize=11,
    )
    fig.tight_layout()
    fig.savefig(path, dpi=140, facecolor="white")
    plt.close(fig)
    return path


def _raster(tris, S: int, np):
    """Z-buffer por pixel. Devolve um array (S, S, 3) de cores RGB.

    Tudo acontece em coordenadas de pixel: vértices, área e teste de
    barycêntrica. Misturar unidades aqui (área em tela, pesos em pixel)
    dá pesos minúsculos e o triângulo inteiro some.
    """
    img = np.ones((S, S, 3), dtype=float)
    zbuf = np.full((S, S), 1e18, dtype=float)
    meio = S / 2.0

    for pts, shade in tris:
        z0, z1, z2 = pts[0][2], pts[1][2], pts[2][2]

        # vértices em pixels, com y invertido (linha 0 = topo da imagem)
        x0, y0 = (pts[0][0] + 1.0) * meio, (1.0 - pts[0][1]) * meio
        x1, y1 = (pts[1][0] + 1.0) * meio, (1.0 - pts[1][1]) * meio
        x2, y2 = (pts[2][0] + 1.0) * meio, (1.0 - pts[2][1]) * meio

        # dobro da área com sinal; zero = triângulo degenerado na tela
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue

        ix0, ix1 = max(0, int(min(x0, x1, x2))), min(S - 1, int(max(x0, x1, x2)) + 1)
        iy0, iy1 = max(0, int(min(y0, y1, y2))), min(S - 1, int(max(y0, y1, y2)) + 1)
        if ix0 > ix1 or iy0 > iy1:
            continue

        cor = (0.34 + 0.50 * shade, 0.48 + 0.32 * shade, 0.62 + 0.28 * shade)

        # arestas em pixels, com o vértice 0 como origem
        ax_, ay_ = x2 - x0, y2 - y0
        bx_, by_ = x1 - x0, y1 - y0

        for iy in range(iy0, iy1 + 1):
            sy = iy + 0.5
            for ix in range(ix0, ix1 + 1):
                sx = ix + 0.5
                # peso de p1 = área do triângulo (p0, p2, P)
                l1 = ((sx - x0) * ay_ - (sy - y0) * ax_) / den
                # peso de p2 = área do triângulo (p0, p1, P)
                l2 = (bx_ * (sy - y0) - by_ * (sx - x0)) / den
                l0 = 1.0 - l1 - l2
                if l0 < 0.0 or l1 < 0.0 or l2 < 0.0:
                    continue
                z = l0 * z0 + l1 * z1 + l2 * z2
                if z < zbuf[iy, ix]:
                    zbuf[iy, ix] = z
                    img[iy, ix] = cor

    return img