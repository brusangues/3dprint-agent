"""Preview visual de um gcode do Cura (imagem estilo Cura: paredes, pele e infill).

Le o gcode, projeta as extrusões em isométrico e desenha um corte de camada do
meio, com legenda. Nao inventa nada: o que aparece sao os movimentos do arquivo.

Uso:
    python tools/gcode_preview.py --gcode out/peca.gcode --out out/peca.png ^
        --titulo "Low Quality 2026" --nota "camada 0.28 mm"
"""

from __future__ import annotations

import argparse
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cotas import cota  # noqa: E402

LINHA = 0.4  # largura de linha do bico 0.4 mm: a linha central da parede fica 0.2 dentro

CORES = {
    "WALL-OUTER": ("#e8453c", 1.0),   # vermelho  - parede externa
    "WALL-INNER": ("#f5a623", 0.9),   # laranja   - paredes internas
    "SKIN": ("#f7d64a", 0.9),         # amarelo   - topo/fundo
    "FILL": ("#4a90d9", 0.75),        # azul      - infill
    "SKIRT": ("#8a8f98", 0.8),        # cinza     - saia
    "SUPPORT": ("#6fbf73", 0.9),
    "BRIM": ("#8a8f98", 0.8),
}
MOVE_RE = re.compile(r"G[01] (?:F[\d.]+ )?X([-\d.]+) Y([-\d.]+)(?: Z([-\d.]+))?(?:.* E([-\d.]+))?$")
ZONLY_RE = re.compile(r"G[01] (?:F[\d.]+ )?Z([-\d.]+)$")


def parse(path: Path):
    """Devolve (camadas, alturas, tempo_s, filamento_mm, metadados do cabecalho).

    O CuraEngine emite o Z da camada numa linha propria *antes* do marcador
    ;LAYER:, entao o Z fica pendente ate o marcador chegar."""
    camadas: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    meta: dict[str, str] = {}
    zs: dict[int, float] = {}
    layer, cur, x, y, last_e = -1, None, 0.0, 0.0, 0.0
    pendente_z: float | None = None
    e_total = 0.0
    elapsed = 0.0
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith(";"):
            if line.startswith(";LAYER:"):
                layer += 1
                if pendente_z is not None:
                    zs[layer] = pendente_z
                    pendente_z = None
            elif line.startswith(";TYPE:"):
                cur = line[6:]
            elif line.startswith(";TIME_ELAPSED:"):
                elapsed = float(line.split(":")[1])
            elif ":" in line:
                k, _, v = line[1:].partition(":")
                meta.setdefault(k.strip(), v.strip())
            continue
        zm = ZONLY_RE.match(line)
        if zm:
            pendente_z = float(zm.group(1))
            continue
        m = MOVE_RE.match(line)
        if not m:
            continue
        nx, ny, nz = float(m.group(1)), float(m.group(2)), m.group(3)
        if nz and layer >= 0:
            zs.setdefault(layer, float(nz))
        if cur is None:
            x, y = nx, ny
            continue
        if m.group(4):
            ev = float(m.group(4))
            if ev > last_e:
                e_total += ev - last_e
                if layer >= 0:
                    camadas[layer][cur].append((x, y, nx, ny))
            last_e = ev
        x, y = nx, ny
    return camadas, zs, elapsed, e_total, meta


def densidade(camadas: dict, layer: int) -> float | None:
    """Densidade efetiva da camada do meio.

    A area do corte e medida na camada solidaria (pele 100%, linhas de 0.4 mm:
    area = comprimento x largura); a do meio usa o mesmo calculo com as linhas de
    infill. Mede o que saiu no arquivo, nao o que o perfil promete."""
    def comprimento(tipo: str, cam: int) -> float:
        return sum(math.dist((s[0], s[1]), (s[2], s[3])) for s in camadas[cam].get(tipo, []))

    cheia = max(camadas, key=lambda l: comprimento("SKIN", l))
    area = comprimento("SKIN", cheia) * 0.4
    if area <= 0:
        return None
    cheia_len = comprimento("SKIN", layer)
    return (cheia_len + comprimento("FILL", layer)) * 0.4 / area * 100


def iso(x: float, y: float, z: float, zscale: float = 1.0):
    return (x - y) * math.cos(math.radians(30)), (x + y) * math.sin(math.radians(30)) + z * zscale


def desenhar(gcode: Path, out: Path, titulo: str, nota: str, painel_infill: bool,
             zscale: float = 5.0, peca: tuple[float, float, float] | None = None,
             furo: tuple[float, float] | None = None) -> dict:
    camadas, zs, elapsed, filamento, meta = parse(gcode)
    topo = max(camadas)
    contorno_medido = None

    def comp(tipo: str, cam: int) -> float:
        return sum(math.dist((s[0], s[1]), (s[2], s[3])) for s in camadas[cam].get(tipo, []))

    # camada "tipica" de infill: a de comprimento mediano (nao a ultima, que leva
    # pele de apoio por cima e mede o dobro)
    cheias = sorted((l for l in camadas if len(camadas[l].get("FILL", [])) > 20), key=lambda l: comp("FILL", l))
    meio = cheias[len(cheias) // 2] if cheias else topo // 2
    dens = densidade(camadas, meio)

    largura_painel = 2 if painel_infill else 1
    fig, axes = plt.subplots(1, largura_painel, figsize=(7.4 * largura_painel, 7.6), dpi=140)
    axes = [axes] if largura_painel == 1 else list(axes)

    # --- painel 1: isometrico, camada por camada (pintor) ---
    ax = axes[0]
    px: list[float] = []
    py: list[float] = []
    for layer in sorted(camadas):
        z = zs.get(layer, 0.0)
        for tipo, segs in camadas[layer].items():
            cor, alfa = CORES.get(tipo, ("#999999", 0.7))
            linhas = []
            for s in segs:
                a = iso(s[0], s[1], z, zscale)
                b = iso(s[2], s[3], z, zscale)
                px += [a[0], b[0]]
                py += [a[1], b[1]]
                linhas.append([a, b])
            ax.add_collection(LineCollection(linhas, colors=cor, linewidths=0.42,
                                             alpha=min(1.0, alfa + 0.1 * layer / max(1, topo)),
                                             zorder=layer + 2))
    if px:
        mx, my = (max(px) - min(px)) * 0.04, (max(py) - min(py)) * 0.04
        ax.set_xlim(min(px) - mx, max(px) + mx)
        ax.set_ylim(min(py) - my, max(py) + my * 2.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"vista isométrica — {topo + 1} camadas (altura ×{zscale:g} para enxergar as camadas)",
                 fontsize=11, pad=10)

    if painel_infill:
        # --- painel 2: corte da camada do meio, visto de cima ---
        ax2 = axes[1]
        for tipo in ("SKIRT", "FILL", "SKIN", "WALL-INNER", "WALL-OUTER"):
            segs = camadas[meio].get(tipo, [])
            if not segs:
                continue
            cor, alfa = CORES.get(tipo, ("#999999", 0.7))
            ax2.add_collection(LineCollection([[list((s[0], s[1])), list((s[2], s[3]))] for s in segs],
                                              colors=cor, linewidths=0.8, alpha=max(0.55, alfa)))
        xs = [p for l in camadas for s in camadas[l].get("WALL-OUTER", []) for p in (s[0], s[2])]
        ys = [p for l in camadas for s in camadas[l].get("WALL-OUTER", []) for p in (s[1], s[3])]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        medido = (max(xs) - min(xs) + LINHA, max(ys) - min(ys) + LINHA)  # linha central + largura
        contorno_medido = medido
        meia = max(medido) / 2 * (1.35 if peca else 1.15)
        ax2.set_xlim(cx - meia, cx + meia)
        ax2.set_ylim(cy - meia, cy + meia)
        ax2.set_aspect("equal")
        ax2.axis("off")
        ax2.set_title(f"corte da camada {meio} (vista de cima, cotas em mm)", fontsize=11, pad=10)
        if peca:
            larg, prof = peca[0], peca[1]
            meia_l, meia_p = larg / 2, prof / 2
            contorno = ((cx - meia_l, cy - meia_p), (cx + meia_l, cy - meia_p),
                        (cx + meia_l, cy + meia_p), (cx - meia_l, cy + meia_p))
            ax2.add_patch(MplPolygon(contorno, closed=True, fc="none", ec="#1b1f24",
                                     lw=1.1, ls=(0, (4, 2)), zorder=3))
            desloc = meia * 0.42
            cota(ax2, contorno[0], contorno[1], f"{larg:g}", offset=-desloc)
            cota(ax2, contorno[0], contorno[3], f"{prof:g}", offset=-desloc)
            if furo:
                fx, fy = furo[0] / 2, furo[1] / 2
                h = ((cx - fx, cy - fy), (cx + fx, cy - fy), (cx + fx, cy + fy), (cx - fx, cy + fy))
                ax2.add_patch(MplPolygon(h, closed=True, fc="none", ec="#1b1f24",
                                         lw=1.1, ls=(0, (4, 2)), zorder=3))
                cota(ax2, h[0], h[1], f"{furo[0]:g}", offset=-desloc * 0.5)
                cota(ax2, h[0], h[3], f"{furo[1]:g}", offset=-desloc * 0.5)
                cota(ax2, (contorno[0][0], h[0][1]), (h[0][0], h[0][1]),
                     f"{(larg - furo[0]) / 2:g}", offset=-desloc * 0.5)
                cota(ax2, (contorno[3][0], h[0][1]), (contorno[3][0], h[3][1]),
                     f"{(prof - furo[1]) / 2:g}", offset=desloc * 0.5)

    dens_txt = f"infill medido {dens:.0f}%" if dens else "infill não medido"
    linhas_meta = [
        f"arquivo: {gcode.name}",
        f"{titulo}  ·  camada {meta.get('Layer height', '?')} mm  ·  {topo + 1} camadas  ·  {dens_txt}",
        f"filamento {filamento / 1000:.2f} m ({filamento * 2.405 * 1.24 / 1000:.1f} g)"
        f"  ·  tempo estimado {elapsed / 60:.0f} min  ·  mesa {meta.get('TARGET_MACHINE.NAME', '?')}",
    ]
    if nota:
        linhas_meta.append(nota)
    fig.suptitle(f"G-code — {gcode.name}", fontsize=15, fontweight="bold", y=0.975)
    altura = 0.155
    for i, linha in enumerate(linhas_meta):
        fig.text(0.5, altura - i * 0.026, linha, ha="center", va="center",
                 fontsize=10.5, color="#333333")
    legenda = ""
    if legenda:
        fig.text(0.5, 0.028, legenda, ha="center", va="center", fontsize=9.5, color="#555555")
    fig.text(0.5, 0.008, "gerado com CuraEngine 5.13 a partir do perfil da sua instalação do Cura",
             ha="center", va="center", fontsize=8.5, color="#888888")
    fig.subplots_adjust(top=0.90, bottom=0.21, left=0.02, right=0.98)
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    return {"gcode": str(gcode), "png": str(out), "camadas": topo + 1, "densidade_medida": dens,
            "contorno_medido": contorno_medido,
            "filamento_m": round(filamento / 1000, 2), "minutos": round(elapsed / 60, 1),
            "gramas": round(filamento * 2.405 * 1.24 / 1000, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gcode", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--titulo", default="")
    ap.add_argument("--nota", default="")
    ap.add_argument("--sem-corte", action="store_true")
    ap.add_argument("--zscale", type=float, default=18.0,
                    help="exagero da altura na vista isometrica (peca chata some em 1x)")
    ap.add_argument("--peca", default="", help="dimensoes nominais WxD[xH] para as cotas, ex.: 60x40x6")
    ap.add_argument("--furo", default="", help="furo da peca para as cotas, ex.: 20x20")
    args = ap.parse_args()
    peca = tuple(float(v) for v in args.peca.lower().split("x")) if args.peca else None
    furo = tuple(float(v) for v in args.furo.lower().split("x")) if args.furo else None
    info = desenhar(Path(args.gcode).resolve(), Path(args.out).resolve(), args.titulo, args.nota,
                    painel_infill=not args.sem_corte, zscale=args.zscale, peca=peca, furo=furo)
    for k, v in info.items():
        print(f"  {k} = {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
