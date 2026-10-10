"""Desenho técnico de um STL, com cotas: 3D + vista superior + vista frontal.

Le a malha do próprio arquivo e MEDE as features antes de desenhar: contorno,
vazio interno (bolsão no topo, furo passante ou rasgo que abre na ponta) e
aba/pé. Se a medida não bater com o que foi pedido, avisa em vez de desenhar
bonito.

Funciona nas duas orientações: em pé (vazio afundado no topo, pé embaixo) e
deitada (vazio abrindo na ponta, aba lateral).

Uso:
    python tools/desenho_stl.py --stl out/peca.stl --out out/cotas.png \
        --largura 17 --profundidade 14 --altura 60 --bolsao 9x6x20 --pe 4x4x3
    python tools/desenho_stl.py --stl out/peca_deitada.stl --out out/cotas.png \
        --largura 17 --comprimento 63 --altura 14.3 --vazio 9.4x6.3x20 --aba 4x3x4
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
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

from cotas import cota  # noqa: E402
from print3d.stl import read_stl  # noqa: E402
from print3d.validate import validate_mesh  # noqa: E402

TOL = 0.05
LARANJA = "#b06a12"


def _normais(malha):
    """(p0, p1, p2, normal) por face."""
    for a, b, c in malha.faces:
        p0, p1, p2 = malha.vertices[a], malha.vertices[b], malha.vertices[c]
        u = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        w = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
        n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
        yield p0, p1, p2, n


def medidas(malha) -> dict:
    """Mede bbox e classifica vazio interno e aba."""
    lo, hi = malha.bbox_min(), malha.bbox_max()
    (x0, x1), (y0, y1), (z0, z1) = (lo[0], hi[0]), (lo[1], hi[1]), (lo[2], hi[2])

    def dentro(v, eixo, a, b):
        return a + TOL < v[eixo] < b - TOL

    t = {"lo": lo, "hi": hi,
         "largura": x1 - x0, "profundidade": y1 - y0, "altura": z1 - z0,
         "volume": abs(malha.volume()), "faces": malha.n_faces,
         "vazio": None, "aba": None, "passante": None}

    # faces por tipo, com faixas
    horiz, vert = [], []   # horiz: (z, nz>0, xa, xb, ya, yb) | vert: (eixo, pos, a0, a1, zmin, zmax)
    for p0, p1, p2, n in _normais(malha):
        pts = (p0, p1, p2)
        fx = (min(p[0] for p in pts), max(p[0] for p in pts))
        fy = (min(p[1] for p in pts), max(p[1] for p in pts))
        fz = (min(p[2] for p in pts), max(p[2] for p in pts))
        nx_, ny_, nz_ = n
        if abs(nx_) < 1e-9 and abs(ny_) < 1e-9 and abs(nz_) > 1e-9:
            horiz.append((p0[2], nz_ > 0, *fx, *fy))
        elif abs(nz_) < 1e-9:
            if abs(nx_) > 1e-9:                       # parede em x
                vert.append(("x", p0[0], fy, fz))
            else:                                     # parede em y
                vert.append(("y", p0[1], fx, fz))
            vert[-1] = (vert[-1][0], vert[-1][1], vert[-1][2], fz)

    def paredes_do_perimetro(z, xa, xb, ya, yb):
        """Paredes verticais encostadas na borda dessa face horizontal."""
        out = []
        for eixo, pos, faixa_outro, fz in vert:
            if eixo == "x":
                if not (abs(pos - xa) < TOL or abs(pos - xb) < TOL):
                    continue
                if abs(faixa_outro[0] - ya) > TOL or abs(faixa_outro[1] - yb) > TOL:
                    continue
            else:
                if not (abs(pos - ya) < TOL or abs(pos - yb) < TOL):
                    continue
                if abs(faixa_outro[0] - xa) > TOL or abs(faixa_outro[1] - xb) > TOL:
                    continue
            out.append(fz)
        return out

    def sobe_acima(z, xa, xb, ya, yb):
        return any(fz[1] > z + TOL for fz in paredes_do_perimetro(z, xa, xb, ya, yb))

    def desce_abaixo(z, xa, xb, ya, yb):
        return any(fz[0] < z - TOL for fz in paredes_do_perimetro(z, xa, xb, ya, yb))

    # piso de vazio: face +z com parede subindo acima dela (o oposto é o topo de um
    # sólido, tipo o topo de uma aba). Teto de vazio: −z com parede descendo abaixo.
    pisos = [h for h in horiz if h[1] and h[0] > z0 + TOL and sobe_acima(h[0], h[2], h[3], h[4], h[5])]
    tetos = [h for h in horiz if not h[1] and h[0] < z1 - TOL and desce_abaixo(h[0], h[2], h[3], h[4], h[5])]
    abas = [h for h in horiz if not h[1] and z0 + TOL < h[0] < z1 - TOL
            and not desce_abaixo(h[0], h[2], h[3], h[4], h[5])]

    def lados_que_encostam(xa, xb, ya, yb):
        return [nome for nome, encosta in (("−x", abs(xa - x0) < TOL), ("+x", abs(xb - x1) < TOL),
                                           ("−y", abs(ya - y0) < TOL), ("+y", abs(yb - y1) < TOL))
                if encosta]

    # --- vazio: piso (+ teto, quando o rasgo abre na lateral) ---
    if pisos:
        zf, _, fxa, fxb, fya, fyb = max(pisos, key=lambda h: -h[0])
        par = [c for c in tetos if abs(c[2] - fxa) < TOL and abs(c[3] - fxb) < TOL
               and abs(c[4] - fya) < TOL and abs(c[5] - fyb) < TOL]
        zc = min(c[0] for c in par) if par else z1
        lados = lados_que_encostam(fxa, fxb, fya, fyb)
        if par:
            abre = f"face {lados[0]}" if lados else "topo"
        elif len(lados) >= 2:
            abre = f"topo, pontas {lados[0]} e {lados[-1]}"
        elif lados:
            abre = f"topo, ponta {lados[0]}"
        else:
            abre = "topo"
        t["vazio"] = {"x": (fxa, fxb), "y": (fya, fyb), "z": (zf, zc),
                      "abre": abre, "prof": zc - zf}

    # --- furo passante: vazio nas duas pontas com a mesma seção ---
    dentro_min = [v for v in malha.vertices if abs(v[2] - z0) < TOL
                  and x0 + TOL < v[0] < x1 - TOL and y0 + TOL < v[1] < y1 - TOL]
    verts_max = [v for v in malha.vertices if abs(v[2] - z1) < TOL
                 and x0 + TOL < v[0] < x1 - TOL and y0 + TOL < v[1] < y1 - TOL]
    if dentro_min and verts_max and not t["vazio"]:
        mn = (min(v[0] for v in dentro_min), max(v[0] for v in dentro_min))
        mx = (min(v[0] for v in verts_max), max(v[0] for v in verts_max))
        if abs(mn[0] - mx[0]) < TOL:
            t["passante"] = {"x": mn, "y": (min(v[1] for v in dentro_min), max(v[1] for v in dentro_min)),
                             "z": (z0, z1), "prof": z1 - z0, "abre": "furo passante"}

    # --- aba lateral: fundo (−z) sem parede descendo, com teto (+z) da mesma seção ---
    for z, _, ax0, ax1, ay0, ay1 in sorted(abas):
        if ax1 - ax0 < 0.5 or ay1 - ay0 < 0.5:
            continue   # face interna de espessura nula (chanfro comeu) não é aba
        par = [h for h in horiz if h[1] and abs(h[0] - z) > TOL and abs(h[2] - ax0) < TOL
               and abs(h[3] - ax1) < TOL and abs(h[4] - ay0) < TOL and abs(h[5] - ay1) < TOL]
        if par:
            t["aba"] = {"x": (ax0, ax1), "y": (ay0, ay1), "z": (z, min(p[0] for p in par)),
                        "eixo": "y" if abs(ay0 - y0) < TOL or abs(ay1 - y1) < TOL else "x"}
            break

    # --- pé embaixo (peça em pé): vazio no z mínimo com corpo acima ---
    corpo_base = [v[2] for v in malha.vertices if v[2] > z0 + TOL
                  and not (x0 + TOL < v[0] < x1 - TOL and y0 + TOL < v[1] < y1 - TOL)]
    if not t["aba"] and not t["passante"] and dentro_min and corpo_base:
        topo_pe = min(corpo_base)
        px0, px1 = min(v[0] for v in dentro_min), max(v[0] for v in dentro_min)
        py0, py1 = min(v[1] for v in dentro_min), max(v[1] for v in dentro_min)
        if px1 - px0 > 0.5 and py1 - py0 > 0.5:   # chanfro toca o z mínimo: não é pé
            t["aba"] = {"x": (px0, px1), "y": (py0, py1),
                        "z": (z0, topo_pe), "eixo": "z"}
    return t


def _projetar(ax, malha, eixos, cor_fundo="#eef1f5", cor_borda="#ccd3dd"):
    """Silhueta verdadeira: projeta cada face no plano indicado."""
    for a, b, c in malha.faces:
        pts = [malha.vertices[i] for i in (a, b, c)]
        ax.add_patch(MplPolygon([(p[eixos[0]], p[eixos[1]]) for p in pts], closed=True,
                                fc=cor_fundo, ec=cor_borda, lw=0.35, zorder=1))


def _cadeia(ax, pontos, valores, offset, total=None, **kw):
    """Cota encadeada: pula trecho de comprimento zero, pula o que já é o total
    (não repetir a mesma medida) e escalona os rótulos, senão trecho curto
    (parede de 1,8 mm) tem o texto por cima do vizinho."""
    for i in range(len(pontos) - 1):
        valor = valores[i]
        if abs(valor) < 0.02:
            continue
        if total and abs(valor - total) < 0.02:
            continue
        extra = (abs(offset) * 0.6) if (total is not None and i % 2) else 0.0
        desloc = offset - extra if offset < 0 else offset + extra
        cota(ax, pontos[i], pontos[i + 1], f"{valor:g}", offset=desloc, **kw)


def desenhar(stl: Path, out: Path, nominal: dict) -> dict:
    malha = read_stl(stl)
    m = medidas(malha)
    rel = validate_mesh(malha)
    lo, hi = m["lo"], m["hi"]
    larg, prof, alt = m["largura"], m["profundidade"], m["altura"]
    vazio, aba = m["vazio"] or m["passante"], m["aba"]

    avisos: list[str] = []

    def confere(nome, medido, esperado):
        if esperado and abs(medido - esperado) > 1e-3:
            avisos.append(f"{nome}: medido {medido:.3f} != pedido {esperado:.3f}")

    confere("largura", larg, nominal.get("largura"))
    confere("comprimento", prof, nominal.get("comprimento"))
    confere("altura", alt, nominal.get("altura"))
    if vazio and nominal.get("vazio"):
        confere("vazio x", vazio["x"][1] - vazio["x"][0], nominal["vazio"][0])
        confere("vazio y", vazio["y"][1] - vazio["y"][0], nominal["vazio"][1])
        confere("vazio z", vazio["z"][1] - vazio["z"][0], nominal["vazio"][2])
    if aba and nominal.get("aba"):
        confere("aba x", aba["x"][1] - aba["x"][0], nominal["aba"][0])
        confere("aba y", aba["y"][1] - aba["y"][0], nominal["aba"][1])
        confere("aba z", aba["z"][1] - aba["z"][0], nominal["aba"][2])

    fig = plt.figure(figsize=(17.0, 6.6), dpi=140)
    axes = [fig.add_subplot(1, 3, 1, projection="3d"),
            fig.add_subplot(1, 3, 2),
            fig.add_subplot(1, 3, 3)]

    # ---------------- 3D ----------------
    ax = axes[0]
    tris = [[malha.vertices[i] for i in f] for f in malha.faces]
    cores = []
    for (ax_, ay, az), (bx, by, bz), (cx, cy, cz) in tris:
        u = (bx - ax_, by - ay, bz - az)
        w = (cx - ax_, cy - ay, cz - az)
        nx, ny, nz = u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]
        ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        luz = 0.42 + 0.5 * abs(nz / ln) + 0.12 * max(0.0, nx / ln)
        cores.append((min(1.0, luz) * 0.62 + 0.18,) * 3)
    ax.add_collection3d(Poly3DCollection(tris, facecolors=cores, edgecolors="#3b4048", linewidths=0.3))
    cx0, cy0, cz0 = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2
    raio = max(larg, prof, alt) * 0.62
    ax.set_xlim(cx0 - raio, cx0 + raio)
    ax.set_ylim(cy0 - raio, cy0 + raio)
    ax.set_zlim(cz0 - raio, cz0 + raio)
    ax.set_box_aspect((larg, prof, alt))
    ax.view_init(elev=30, azim=-64)
    ax.set_axis_off()
    ax.set_title("3D (malha do STL)", fontsize=11, pad=2)

    # ---------------- vista superior (X-Y) ----------------
    ax2 = axes[1]
    _projetar(ax2, malha, (0, 1))
    margem = max(larg, prof) * 0.20
    x0, x1, y0, y1 = lo[0], hi[0], lo[1], hi[1]
    if vazio:
        vx0, vx1 = vazio["x"]
        vy0, vy1 = vazio["y"]
        ax2.add_patch(MplPolygon([(vx0, vy0), (vx1, vy0), (vx1, vy1), (vx0, vy1)], closed=True,
                                 fc="white", ec="#1b1f24", lw=1.7, zorder=3))
        ax2.text((vx0 + vx1) / 2, (vy0 + vy1) / 2 + margem * 0.08,
                 f"{vazio['x'][1] - vazio['x'][0]:g} × {vazio['y'][1] - vazio['y'][0]:g}"
                 f"\n{vazio['abre']}",
                 ha="center", va="center", fontsize=8.5, color="#1b1f24", zorder=6)
        _cadeia(ax2, [(x0, vy0), (vx0, vy0), (vx1, vy0), (x1, vy0)],
                [vx0 - x0, vx1 - vx0, x1 - vx1], -margem * 0.36, total=larg)
        _cadeia(ax2, [(x1, y0), (x1, vy0), (x1, vy1), (x1, y1)],
                [vy0 - y0, vy1 - vy0, y1 - vy1], margem * 0.44, total=prof)
    if aba:
        ax2.add_patch(MplPolygon([(aba["x"][0], aba["y"][0]), (aba["x"][1], aba["y"][0]),
                                  (aba["x"][1], aba["y"][1]), (aba["x"][0], aba["y"][1])],
                                 closed=True, fc="none", ec=LARANJA, lw=1.5, ls=(0, (4, 2)), zorder=5))
        cota(ax2, (aba["x"][0], aba["y"][0]), (aba["x"][1], aba["y"][0]),
             f"{aba['x'][1] - aba['x'][0]:g}", offset=-margem * 0.78,
             cor=LARANJA, fonte_borda="#fff8ee")
        if aba["eixo"] == "y":
            cota(ax2, (aba["x"][0], aba["y"][0]), (aba["x"][0], aba["y"][1]),
                 f"{aba['y'][1] - aba['y'][0]:g}", offset=-margem * 0.30,
                 cor=LARANJA, fonte_borda="#fff8ee")
    ax2.set_xlim(x0 - margem * 1.3, x1 + margem * 1.0)
    ax2.set_ylim(y0 - margem * 1.8, y1 + margem * 0.8)
    ax2.set_aspect("equal")
    ax2.axis("off")
    ax2.set_title("vista superior (mm)", fontsize=11, pad=2)
    cota(ax2, (x0, y0), (x1, y0), f"{larg:g}", offset=-margem * 1.05)
    cota(ax2, (x0, y0), (x0, y1), f"{prof:g}", offset=-margem * 0.95)

    # ---------------- vista frontal (X-Z) ----------------
    ax3 = axes[2]
    _projetar(ax3, malha, (0, 2))
    margem3 = max(larg, alt) * 0.22
    if vazio:
        vz0, vz1 = vazio["z"]
        vx0, vx1 = vazio["x"]
        ax3.add_patch(MplPolygon([(vx0, vz0), (vx1, vz0), (vx1, vz1), (vx0, vz1)], closed=True,
                                 fc="none", ec="#1b1f24", lw=1.2, ls=(0, (5, 3)), zorder=3))
        _cadeia(ax3, [(x0, lo[2]), (x0, vz0), (x0, vz1), (x0, hi[2])],
                [vz0 - lo[2], vz1 - vz0, hi[2] - vz1], -margem3 * 0.95, total=alt)
    if aba:
        ax3.add_patch(MplPolygon([(aba["x"][0], aba["z"][0]), (aba["x"][1], aba["z"][0]),
                                  (aba["x"][1], aba["z"][1]), (aba["x"][0], aba["z"][1])],
                                 closed=True, fc="none", ec=LARANJA, lw=1.5, ls=(0, (4, 2)), zorder=4))
        cota(ax3, (aba["x"][1], aba["z"][0]), (aba["x"][1], aba["z"][1]),
             f"{aba['z'][1] - aba['z'][0]:g}", offset=margem3 * 0.22,
             cor=LARANJA, fonte_borda="#fff8ee")
    ax3.set_xlim(x0 - margem3 * 1.6, x1 + margem3 * 1.2)
    ax3.set_ylim(lo[2] - margem3 * 0.9, hi[2] + margem3 * 0.6)
    ax3.set_aspect("equal")
    ax3.axis("off")
    ax3.set_title("vista frontal (mm)", fontsize=11, pad=2)
    cota(ax3, (x0, lo[2]), (x1, lo[2]), f"{larg:g}", offset=-margem3 * 0.6)
    cota(ax3, (x1, lo[2]), (x1, hi[2]), f"{alt:g}", offset=margem3 * 0.85)

    # ---------------- rodapé ----------------
    partes = [f"{larg:g} × {prof:g} × {alt:g} mm"]
    if vazio:
        partes.append(f"vazio {vazio['x'][1] - vazio['x'][0]:g} × {vazio['y'][1] - vazio['y'][0]:g}"
                      f" × {vazio['z'][1] - vazio['z'][0]:g} mm ({vazio['abre']})")
    if aba:
        partes.append(f"aba {aba['x'][1] - aba['x'][0]:g} × {aba['y'][1] - aba['y'][0]:g}"
                      f" × {aba['z'][1] - aba['z'][0]:g} mm (traço laranja)")
    infos = [
        f"arquivo: {stl.name}",
        "  ·  ".join(partes),
        f"volume {m['volume']:,.2f} mm³  ·  {m['faces']} faces  ·  "
        f"{'malha fechada, winding ok' if rel.ok else 'MALHA REPROVADA: ' + rel.summary()}",
    ]
    if avisos:
        infos.append("ATENÇÃO: " + " | ".join(avisos))
    fig.suptitle(f"Desenho da peça — {stl.name}", fontsize=15, fontweight="bold", y=0.985)
    for i, linha in enumerate(infos):
        fig.text(0.5, 0.105 - i * 0.028, linha, ha="center", va="center", fontsize=10, color="#333333")
    fig.subplots_adjust(top=0.90, bottom=0.19, left=0.02, right=0.98, wspace=0.05)
    fig.savefig(out, facecolor="white")
    plt.close(fig)

    return {"png": str(out), "largura": larg, "comprimento": prof, "altura": alt,
            "vazio": vazio, "aba": aba, "volume": m["volume"], "malha_ok": rel.ok,
            "avisos": avisos}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--largura", type=float, required=True)
    ap.add_argument("--altura", type=float, required=True)
    ap.add_argument("--profundidade", type=float, help="peça em pé: comprimento em Y")
    ap.add_argument("--comprimento", type=float, help="peça deitada: comprimento em Y")
    ap.add_argument("--bolsao", default="", help="vazio WxDxH, ex.: 9x6x20")
    ap.add_argument("--vazio", default="", help="igual a --bolsao (nome neutro)")
    ap.add_argument("--furo", default="", help="furo passante WxD, ex.: 20x20")
    ap.add_argument("--pe", default="", help="pé/aba WxDxH, ex.: 4x4x3")
    ap.add_argument("--aba", default="", help="igual a --pe (nome neutro)")
    args = ap.parse_args()

    def parse(texto, n):
        if not texto:
            return None
        valores = [float(v) for v in texto.lower().split("x")]
        return tuple(valores) if len(valores) == n else None

    nominal = {"largura": args.largura,
               "comprimento": args.comprimento or args.profundidade,
               "altura": args.altura,
               "vazio": parse(args.vazio or args.bolsao, 3),
               "furo": parse(args.furo, 2),
               "aba": parse(args.aba or args.pe, 3)}
    info = desenhar(Path(args.stl).resolve(), Path(args.out).resolve(), nominal)
    for k, v in info.items():
        print(f"  {k} = {v}")
    return 1 if info["avisos"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
