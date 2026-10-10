"""Vista de seção de um STL, com cotas — mostra onde vive o ângulo.

As três vistas do desenho_stl.py (3D, superior, frontal) não mostram uma
parede inclinada no plano Y-Z: a rampa aparece de lado. Esta ferramenta corta
a malha num plano (x ou y) e desenha a seção resultante com as cotas do
contorno, do vazio e, principalmente, o ÂNGULO de cada aresta inclinada —
medido do plano vertical, que é como o usuário pede ("40° na parede").

Uso:
    python tools/secao_stl.py --stl out/peca.stl --out out/peca_secao.png \
        --eixo x --pos 6.5

Precisa do trimesh (usa a mesma cadeia de segmentos do medir_gcode).
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from cotas import cota  # noqa: E402
from medir_gcode import lacos  # noqa: E402

EIXOS = {"x": 0, "y": 1, "z": 2}
HORIZ = {"x": ("y", "z"), "y": ("x", "z"), "z": ("x", "y")}
TOL = 1e-4


def cortar(stl: Path, eixo: str, pos: float):
    """Seção da malha no plano eixo=pos, devolvida em (u, v) = os 2 outros eixos."""
    import trimesh

    malha = trimesh.load(str(stl), force="mesh")
    normal = [0.0, 0.0, 0.0]
    normal[EIXOS[eixo]] = 1.0
    origem = [0.0, 0.0, 0.0]
    origem[EIXOS[eixo]] = pos
    seg = trimesh.intersections.mesh_plane(malha, normal, origem)
    iu, iv = (EIXOS[a] for a in HORIZ[eixo])
    planos = [(float(s[0][iu]), float(s[0][iv]), float(s[1][iu]), float(s[1][iv]))
              for s in seg]
    return lacos(planos)


def bbox(pontos):
    us = [p[0] for p in pontos]
    vs = [p[1] for p in pontos]
    return min(us), max(us), min(vs), max(vs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--eixo", default="x", choices=list(EIXOS))
    ap.add_argument("--pos", type=float, required=True, help="posição do corte no eixo")
    ap.add_argument("--rotulo", default="")
    args = ap.parse_args()

    stl, png = Path(args.stl), Path(args.out)
    u, v = HORIZ[args.eixo]
    lacos_secao = cortar(stl, args.eixo, args.pos)
    if not lacos_secao:
        print("corte vazio: escolha outra posição")
        return 1
    lacos_secao.sort(key=lambda ll: -abs(_area(ll)))
    externo, *internos = lacos_secao

    fig, ax = plt.subplots(figsize=(12, 7), dpi=140)
    fig.patch.set_facecolor("#ffffff")

    def desenhar(laco, cor, largura=1.4, tracejado=None):
        ax.add_patch(MplPolygon(laco, closed=True, fc=cor, ec="#1b1f24",
                                lw=largura, ls=tracejado or "-", zorder=2))

    desenhar(externo, "#eef1f4")
    for buraco in internos:
        desenhar(buraco, "#ffffff")
    for laco in lacos_secao:
        ax.add_patch(MplPolygon(laco, closed=True, fc="none", ec="#1b1f24", lw=1.2, zorder=3))

    u0, u1, v0, v1 = bbox(externo)
    margem = max(u1 - u0, v1 - v0) * 0.18

    # arestas inclinadas: ângulo do plano vertical (eixo v)
    inclinadas = []
    for laco in lacos_secao:
        for i in range(len(laco)):
            a, b = laco[i], laco[(i + 1) % len(laco)]
            du, dv = b[0] - a[0], b[1] - a[1]
            if abs(du) < TOL or abs(dv) < TOL:
                continue
            angulo = math.degrees(math.atan2(abs(du), abs(dv)))
            if 1.0 < angulo < 89.0:
                inclinadas.append((a, b, angulo))

    vistos: set[int] = set()
    for a, b, angulo in inclinadas:
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#c2410c", lw=3.0, zorder=4)
        if round(angulo) in vistos:
            continue          # a rampa vem partida em 2 segmentos: 1 rótulo só
        vistos.add(round(angulo))
        meio = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        ax.annotate(f"{angulo:.0f}°\n(da vertical)", meio,
                    textcoords="offset points", xytext=(18, -26), fontsize=10,
                    color="#c2410c", fontweight="bold", ha="left", va="top",
                    arrowprops=dict(arrowstyle="->", color="#c2410c", lw=1.2), zorder=6)

    # cotas do contorno
    cota(ax, (u0, v0), (u1, v0), f"{u1 - u0:g}", offset=-margem * 0.9)
    cota(ax, (u1, v0), (u1, v1), f"{v1 - v0:g}", offset=margem * 0.9)
    for buraco in internos:
        bu, bv, bv0, bv1 = bbox(buraco)
        cota(ax, (bu, bv0), (bu, bv1), f"{bv1 - bv0:g}", offset=-margem * 0.45)
        cota(ax, (bu, bv0), (bmax := bbox(buraco)[1], bv0), f"{bmax - bu:g}",
             offset=-margem * 0.45)

    ax.set_aspect("equal")
    ax.set_xlim(u0 - margem * 1.7, u1 + margem * 1.7)
    ax.set_ylim(v0 - margem * 1.2, v1 + margem * 1.3)
    ax.axis("off")
    titulo = args.rotulo or f"seção em {args.eixo} = {args.pos:g}"
    ax.set_title(f"{titulo}  ·  {stl.name}\n(u = {u}, v = {v})", fontsize=12,
                 fontweight="bold", color="#1b1f24", pad=12)

    rodape = [f"{stl.name}  ·  corte em {args.eixo} = {args.pos:g} mm",
              f"contorno {u1 - u0:g} × {v1 - v0:g} mm ({u} × {v})",
              f"vazios: {len(internos)}"]
    if inclinadas:
        rodape.append("arestas inclinadas: " +
                      ", ".join(f"{ang:.1f}° da vertical" for _, _, ang in inclinadas))
    fig.text(0.5, 0.015, "  ·  ".join(rodape), ha="center", fontsize=9.5, color="#4b5563")
    fig.subplots_adjust(bottom=0.11, top=0.88)
    fig.savefig(png, facecolor=fig.get_facecolor())
    print(f"png = {png}")
    print(f"contorno {u1 - u0:g} × {v1 - v0:g} mm · vazios {len(internos)}")
    for a, b, ang in inclinadas:
        print(f"  aresta inclinada {a} -> {b}: {ang:.3f}° da vertical")
    return 0


def _area(laco) -> float:
    s = 0.0
    for i in range(len(laco)):
        u1, v1 = laco[i]
        u2, v2 = laco[(i + 1) % len(laco)]
        s += u1 * v2 - u2 * v1
    return s / 2.0


if __name__ == "__main__":
    raise SystemExit(main())
