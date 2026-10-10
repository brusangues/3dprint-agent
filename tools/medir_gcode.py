"""Mede o gcode do jeito que o paquímetro mede: contorno, altura e furos.

Serve quando a peça impressa não corresponde ao STL: se o modelo foi cortado
ou girado dentro do Cura, quem manda é o gcode — é ele que a impressora
executou. Mede o contorno externo e cada vazio no corte de uma camada.

Regra da linha central (bico 0.4 mm): parede externa tem a linha central
0.2 mm dentro do contorno, furo tem 0.2 mm fora do vazio. Então:

    contorno nominal = bbox medido + largura de linha
    furo nominal     = bbox medido - largura de linha

Uso:
    python tools/medir_gcode.py --gcode C:/3dprint/CE3PRO_SIGNAL_CAP_STAND.gcode
    python tools/medir_gcode.py --gcode peca.gcode --camadas 1,50,ultima
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from gcode_preview import parse  # noqa: E402

LINHA = 0.4


def lacos(segs, tol: int = 3) -> list[list[tuple[float, float]]]:
    """Encadeia segmentos (x1,y1,x2,y2) em laços fechados."""
    def k(p):
        return (round(float(p[0]), tol), round(float(p[1]), tol))

    pend: dict[tuple, list[int]] = {}
    for i, s in enumerate(segs):
        pend.setdefault(k((s[0], s[1])), []).append(i)
        pend.setdefault(k((s[2], s[3])), []).append(i)

    usados: set[int] = set()
    saida: list[list[tuple[float, float]]] = []
    for inicio in range(len(segs)):
        if inicio in usados:
            continue
        usados.add(inicio)
        s = segs[inicio]
        pontos = [k((s[0], s[1])), k((s[2], s[3]))]
        partida = pontos[0]
        while pontos[-1] != partida:
            prox = next((i for i in pend.get(pontos[-1], []) if i not in usados), None)
            if prox is None:
                break
            usados.add(prox)
            t = segs[prox]
            atual = k((t[2], t[3])) if k((t[0], t[1])) == pontos[-1] else k((t[0], t[1]))
            if atual != pontos[-1]:
                pontos.append(atual)
        if len(pontos) >= 4:
            saida.append(pontos)
    return saida


def descreve(pontos) -> dict:
    n = len(pontos)
    a2 = 0.0
    cx = cy = 0.0
    for i in range(n):
        x1, y1 = pontos[i]
        x2, y2 = pontos[(i + 1) % n]
        cruz = x1 * y2 - x2 * y1
        a2 += cruz
        cx += (x1 + x2) * cruz
        cy += (y1 + y2) * cruz
    if abs(a2) < 1e-9:
        return {"area": 0.0}
    area = a2 / 2.0
    cx /= 3.0 * a2
    cy /= 3.0 * a2
    xs = [p[0] for p in pontos]
    ys = [p[1] for p in pontos]
    raios = [math.dist(p, (cx, cy)) for p in pontos]
    r = sum(raios) / len(raios)
    return {"area": abs(area), "x": (min(xs), max(xs)), "y": (min(ys), max(ys)),
            "centro": (cx, cy), "redondo": 100.0 * (1 - (max(raios) - min(raios)) / r) if r else 0.0,
            "r": r}


def medir_camada(camadas, layer: int, z: float) -> dict:
    segs = [s for tipo in ("WALL-OUTER", "WALL-INNER", "SKIN", "FILL", "SUPPORT")
            for s in camadas[layer].get(tipo, [])]
    achados = sorted((descreve(p) for p in lacos(segs)), key=lambda d: -d.get("area", 0.0))
    achados = [d for d in achados if d.get("area", 0.0) > 0.5]
    if not achados:
        return {"z": z, "contornos": 0}
    fora = achados[0]
    dados = {"z": z, "contornos": len(achados),
             "externo": {"x": fora["x"][1] - fora["x"][0], "y": fora["y"][1] - fora["y"][0],
                         "nominal_x": fora["x"][1] - fora["x"][0] + LINHA,
                         "nominal_y": fora["y"][1] - fora["y"][0] + LINHA,
                         "centro": fora["centro"], "redondo": fora["redondo"]},
             "vazios": []}
    for d in achados[1:]:
        w = d["x"][1] - d["x"][0]
        h = d["y"][1] - d["y"][0]
        dados["vazios"].append({"w": w, "h": h, "nominal_w": w - LINHA, "nominal_h": h - LINHA,
                                "redondo": d["redondo"], "centro": d["centro"]})
    return dados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gcode", required=True)
    ap.add_argument("--camadas", default="1,50,ultima")
    args = ap.parse_args()

    camadas, zs, elapsed, filamento, meta = parse(Path(args.gcode))
    topo = max(camadas)
    todas = [(l, s) for l in camadas for t in camadas[l] for s in camadas[l][t]]
    xmin = min(min(s[0], s[2]) for _, s in todas)
    xmax = max(max(s[0], s[2]) for _, s in todas)
    ymin = min(min(s[1], s[3]) for _, s in todas)
    ymax = max(max(s[1], s[3]) for _, s in todas)
    zmax = max(zs.values()) if zs else 0.0

    print(f"arquivo    {args.gcode}")
    print(f"cabeçalho  camada {meta.get('Layer height', '?')} mm  ·  {topo + 1} camadas  ·  "
          f"tempo {elapsed / 60:.0f} min  ·  {filamento / 1000:.2f} m de filamento")
    print(f"extrusão   x {xmin:.3f}..{xmax:.3f}   y {ymin:.3f}..{ymax:.3f}   z até {zmax:.3f}")
    print(f"nominal    largura {xmax - xmin + LINHA:.3f} × comprimento {ymax - ymin + LINHA:.3f}"
          f" × altura {zmax:.3f} mm   (contorno + 0.4 de linha; altura = topo da última camada)")

    for pedido in args.camadas.split(","):
        pedido = pedido.strip().lower()
        layer = topo if pedido.startswith("ult") else max(0, round(topo * float(pedido) / 100.0))
        d = medir_camada(camadas, layer, zs.get(layer, 0.0))
        if not d.get("contornos"):
            print(f"\ncamada {layer} (z {d['z']:.3f}): sem contorno fechado (pele/infill sem parede)")
            continue
        e = d["externo"]
        print(f"\ncamada {layer}  z = {d['z']:.3f} mm  ({d['contornos']} contornos)")
        forma = "circular" if e["redondo"] > 97 else "retangular"
        print(f"  externo {forma}: {e['nominal_x']:.3f} × {e['nominal_y']:.3f} mm nominal"
              f"  (medido na linha central {e['x']:.3f} × {e['y']:.3f}, circularidade {e['redondo']:.1f}%)")
        for i, v in enumerate(d["vazios"], start=1):
            forma = "circular" if v["redondo"] > 97 else "retangular"
            print(f"  vazio {i} {forma}: {v['nominal_w']:.3f} × {v['nominal_h']:.3f} mm nominal"
                  f"  (linha central {v['w']:.3f} × {v['h']:.3f})"
                  f"  centro ({v['centro'][0]:.2f}, {v['centro'][1]:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
