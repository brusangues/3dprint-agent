"""Mede um STL do jeito que o paquímetro mede: bbox, corte em altura e furos.

Aqui se mede o ARQUIVO, com o critério da peça pronta: contorno externo
(largura × comprimento) e cada vazio interno (furo), no corte de uma altura
escolhida. Comparar com o paquímetro separa "o arquivo está diferente do
pedido" de "a máquina encolhe".

O corte usa trimesh (seção plana robusta). Rode com o python do env print3d:
    conda run -n print3d python tools/medir_stl.py --stl peca.stl

Uso:
    python tools/medir_stl.py --stl C:/3dprint/ToothPasteStand.stl
    python tools/medir_stl.py --stl peca.stl --cortes 1,50,99
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def laços(secao) -> list:
    """Laços fechados (Nx2) da seção plana, em mm."""
    planar, _ = secao.to_planar()
    return [p for p in planar.discrete if len(p) >= 3]


def lacos_de_segmentos(segs, tol: int = 3) -> list:
    """Encadeia segmentos (n,2,3) em laços fechados no plano xy.

    Usa chave arredondada (1 µm) em vez de igualdade exata: as coordenadas
    vêm de interpolação, então dois triângulos vizinhos não dão bit a bit o
    mesmo ponto."""
    def k(p):
        return (round(float(p[0]), tol), round(float(p[1]), tol))

    pend: dict[tuple, list[int]] = {}
    for i, s in enumerate(segs):
        pend.setdefault(k(s[0]), []).append(i)
        pend.setdefault(k(s[1]), []).append(i)

    usados: set[int] = set()
    lacos: list[list[tuple[float, float]]] = []
    for inicio in range(len(segs)):
        if inicio in usados:
            continue
        usados.add(inicio)
        s = segs[inicio]
        pontos = [k(s[0]), k(s[1])]
        ponta = pontos[-1]
        partida = pontos[0]
        while True:
            if ponta == partida:
                break
            prox = next((i for i in pend.get(ponta, []) if i not in usados), None)
            if prox is None:
                break
            usados.add(prox)
            seg = segs[prox]
            ponta = k(seg[1]) if k(seg[0]) == ponta else k(seg[0])
            if ponta != pontos[-1]:
                pontos.append(ponta)
        if len(pontos) >= 4:  # fecha o último ponto de novo
            if pontos[-1] != pontos[0]:
                pontos.append(pontos[0])
            lacos.append(pontos)
    return lacos



def descreve(pontos) -> dict:
    """Área (shoelace), caixa, centro e raios — para dizer se é círculo."""
    n = len(pontos)
    area2 = 0.0
    cx = cy = 0.0
    for i in range(n):
        x1, y1 = float(pontos[i][0]), float(pontos[i][1])
        x2, y2 = float(pontos[(i + 1) % n][0]), float(pontos[(i + 1) % n][1])
        cruz = x1 * y2 - x2 * y1
        area2 += cruz
        cx += (x1 + x2) * cruz
        cy += (y1 + y2) * cruz
    if abs(area2) < 1e-12:
        return {"area": 0.0}
    area = area2 / 2.0
    cx /= 3.0 * area2
    cy /= 3.0 * area2
    xs = [float(p[0]) for p in pontos]
    ys = [float(p[1]) for p in pontos]
    raios = [math.dist((float(x), float(y)), (cx, cy)) for x, y in pontos]
    r_med = sum(raios) / len(raios)
    return {
        "area": abs(area), "centro": (cx, cy),
        "x": (min(xs), max(xs)), "y": (min(ys), max(ys)),
        "r_min": min(raios), "r_max": max(raios), "r_medio": r_med,
        "redondo_%": 100.0 * (1 - (max(raios) - min(raios)) / r_med) if r_med else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl", required=True)
    ap.add_argument("--cortes", default="1,50,99", help="frações da altura (%), separadas por vírgula")
    args = ap.parse_args()

    try:
        import trimesh
    except ImportError:
        print("precisa de trimesh: conda run -n print3d python tools/medir_stl.py ...")
        return 2

    malha = trimesh.load(args.stl, force="mesh")
    lo, hi = malha.bounds
    larg, prof, alt = hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]
    print(f"arquivo   {args.stl}")
    print(f"malha     {len(malha.faces)} faces, {len(malha.vertices)} vértices, "
          f"água-tight={malha.is_watertight}")
    print(f"volume    {malha.volume:,.2f} mm³")
    print(f"caixa     {larg:.3f} × {prof:.3f} × {alt:.3f} mm  (largura × comprimento × altura)")
    print(f"          x {lo[0]:.3f}..{hi[0]:.3f}   y {lo[1]:.3f}..{hi[1]:.3f}   z {lo[2]:.3f}..{hi[2]:.3f}")

    for frac in (float(v) for v in args.cortes.split(",")):
        z = lo[2] + alt * frac / 100.0
        segs = trimesh.intersections.mesh_plane(
            malha, plane_origin=[0.0, 0.0, z], plane_normal=[0.0, 0.0, 1.0])
        achados = sorted((descreve(p) for p in lacos_de_segmentos(segs)),
                         key=lambda d: -d.get("area", 0.0))
        achados = [d for d in achados if d.get("area", 0.0) > 0.05]
        print(f"\ncorte em z = {z:.3f} mm ({frac:g}% da altura): {len(segs)} segmentos, "
              f"{len(achados)} contorno(s) com área")
        for i, d in enumerate(achados):
            ext = (d["x"][1] - d["x"][0], d["y"][1] - d["y"][0])
            tipo = "contorno externo" if i == 0 else f"vazio interno {i}"
            circulo = d["redondo_%"] > 97
            linha1 = (f"  {tipo}: área {d['area']:.2f} mm²  caixa {ext[0]:.3f} × {ext[1]:.3f} mm"
                      f"  centro ({d['centro'][0]:.2f}, {d['centro'][1]:.2f})")
            print(linha1)
            if circulo:
                print(f"    círculo: diâmetro {2 * d['r_medio']:.3f} mm "
                      f"(mín {2 * d['r_min']:.3f} / máx {2 * d['r_max']:.3f}, "
                      f"circularidade {d['redondo_%']:.1f}%)")
            else:
                print(f"    retangular (circularidade {d['redondo_%']:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
