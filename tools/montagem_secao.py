"""Montagem: corta DUAS peças no mesmo plano e desenha sobrepostas.

Serve para peça macho + fêmea: mostra o encaixe de verdade, com as duas malhas
medidas, não um esquema. O macho sai em cor de destaque.

Uso:
    conda run -n print3d python tools/montagem_secao.py \
        --base out/suporte.stl --macho out/gaveta.stl \
        --eixo y --pos 5.8 --out out/montagem.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from cotas import cota  # noqa: E402
from secao_stl import HORIZ, cortar  # noqa: E402


def bbox(pontos):
    us = [p[0] for p in pontos]
    vs = [p[1] for p in pontos]
    return min(us), max(us), min(vs), max(vs)


def desenha(ax, lacos, cor, rotulo, z):
    lacos = sorted(lacos, key=lambda ll: -abs(_area(ll)))
    for i, laco in enumerate(lacos):
        ax.add_patch(MplPolygon(laco, closed=True, fc=cor if i == 0 else "#ffffff",
                                ec="#1b1f24", lw=1.3, zorder=z, label=rotulo if i == 0 else None))
    return lacos


def _area(laco) -> float:
    s = 0.0
    for i in range(len(laco)):
        u1, v1 = laco[i]
        u2, v2 = laco[(i + 1) % len(laco)]
        s += u1 * v2 - u2 * v1
    return s / 2.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="peça fêmea (o suporte que ele já tem)")
    ap.add_argument("--macho", required=True, help="peça que entra nela")
    ap.add_argument("--out", required=True)
    ap.add_argument("--eixo", default="y", choices=list(HORIZ))
    ap.add_argument("--pos", type=float, required=True)
    ap.add_argument("--rotulo-base", default="peça que ele já tem (fêmea)")
    ap.add_argument("--rotulo-macho", default="peça nova (macho)")
    ap.add_argument("--offset", default="0,0,0",
                    help="dx,dy,dz para o macho entrar no referencial da fêmea")
    args = ap.parse_args()

    dx, dy, dz = (float(v) for v in args.offset.split(","))
    base, macho = Path(args.base), Path(args.macho)
    # o macho está medido no referencial dele: corta na posição equivalente e
    # desloca os pontos para o referencial da fêmea, senão a sobreposição não diz nada
    if args.eixo == "x":
        pos_macho, desloc = args.pos - dx, (dy, dz)
    elif args.eixo == "y":
        pos_macho, desloc = args.pos - dy, (dx, dz)
    else:
        pos_macho, desloc = args.pos - dz, (dx, dy)
    lb = cortar(base, args.eixo, args.pos)
    lm = [[(p[0] + desloc[0], p[1] + desloc[1]) for p in laco]
          for laco in cortar(macho, args.eixo, pos_macho)]
    if not lb or not lm:
        print("um dos cortes ficou vazio nessa posição")
        return 1

    u, v = HORIZ[args.eixo]
    fig, ax = plt.subplots(figsize=(12, 8), dpi=140)
    fig.patch.set_facecolor("white")
    desenha(ax, lb, "#dbe3ec", args.rotulo_base, z=2)
    desenha(ax, lm, "#f8b26a", args.rotulo_macho, z=3)

    todos = [p for laco in lb + lm for p in laco]
    u0, u1, v0, v1 = bbox(todos)
    margem = max(u1 - u0, v1 - v0) * 0.16
    ax.set_aspect("equal")
    ax.set_xlim(u0 - margem * 1.8, u1 + margem * 1.8)
    ax.set_ylim(v0 - margem * 1.2, v1 + margem * 1.3)
    ax.axis("off")
    ax.legend(loc="upper left", fontsize=10, frameon=True)
    ax.set_title("montagem · corte em %s = %g  ·  %s + %s"
                 % (args.eixo, args.pos, base.name, macho.name),
                 fontsize=12, fontweight="bold", pad=12)

    cota(ax, (u0, v0), (u1, v0), "%.2f" % (u1 - u0), offset=-margem * 0.85)
    cota(ax, (u1, v0), (u1, v1), "%.2f" % (v1 - v0), offset=margem * 0.85)
    fig.text(0.5, 0.02, "u = %s, v = %s · as duas peças medidas do próprio STL"
             % (u, v), ha="center", fontsize=9.5, color="#4b5563")
    fig.subplots_adjust(bottom=0.08, top=0.9)
    fig.savefig(args.out, facecolor="white")
    print("png = %s" % args.out)
    print("corte: base %d laço(s), macho %d laço(s)" % (len(lb), len(lm)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
