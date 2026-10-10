"""Versão deitada (para impressão) da coluna 17 x 14 x 60, com tolerâncias compensadas.

Uso:
    conda run -n print3d python examples/make_extensor_braco_suporte_notebook_deitada.py

Orientação: deitada sobre a face de 17 x 63, então o eixo de 63 mm fica
horizontal e a ALTURA impressa é o lado de 14 mm. O bolsão passa a abrir na
ponta, não no topo; o pé deixa de encostar na mesa e vira aba lateral.

Compensação (medida nas duas peças reais, skill gerar-pecas-3d):

  eixo                         nominal  desenhado   por quê
  comprimento 63 (horizontal)    63,0      63,0     XY sai nominal
  largura 17 (horizontal)        17,0      17,0     XY sai nominal
  altura 14 (vertical)           14,0      14,3     perda vertical ~0,3 mm
  vazio 9 (horizontal)            9,0       9,4     furo encolhe ~0,4 mm
  vazio 6 (vertical)              6,0       6,3     teto é ponte e cede p/ dentro
  vazio 20 (profundidade horiz.) 20,0      20,0     horizontal
  pé 4 (largura)                  4,0       4,0     sem pé de elefante (não toca a mesa)
  pé 4 (vertical)                 4,0       4,0     idem
  pé 3 (saliencia horizontal)     3,0       3,0     horizontal

Volume: 17*60*14,3 - 9,4*20*6,3 + 4*3*4
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from print3d import csg, primitives as prim  # noqa: E402
from print3d.stl import write_obj, write_stl, write_stl_ascii  # noqa: E402
from print3d.validate import validate_mesh  # noqa: E402

# eixos da peça deitada: X = largura, Y = comprimento (horizontal), Z = altura
LARGURA = 17.0            # nominal
COMPRIMENTO = 63.0        # nominal (3 do pé + 60 do corpo)
ALTURA = 14.3             # 14 + 0,3 de compensação vertical
CORPO_Y = 60.0            # corpo, sem o pé
PE_Y = 3.0                # saliência do pé
PE_X = 4.0
PE_Z = 4.0
VOID_X = 9.4              # 9 + 0,4
VOID_Z = 6.3              # 6 + 0,3
VOID_Y = 20.0             # profundidade, horizontal: nominal
VOID_Z_FLOOR = 4.3        # distância do fundo do vazio até a mesa
PE_Z0 = (ALTURA - PE_Z) / 2  # pé centrado na altura


def euler(malha) -> int:
    arestas = set()
    for a, b, c in malha.faces:
        for u, v in ((a, b), (b, c), (c, a)):
            ku = tuple(round(x, 5) for x in malha.vertices[u])
            kv = tuple(round(x, 5) for x in malha.vertices[v])
            arestas.add((ku, kv) if ku < kv else (kv, ku))
    verts = {tuple(round(x, 5) for x in v) for v in malha.vertices}
    return len(verts) - len(arestas) + malha.n_faces


def main() -> int:
    if not csg.csg_available():
        print("CSG indisponível: pip install trimesh manifold3d")
        return 1

    raiz = Path(__file__).resolve().parents[1]
    out = raiz / "out"
    out.mkdir(exist_ok=True)

    # corpo: começa em Y = 3 (o pé ocupa 0..3) e sobe toda a altura
    corpo = prim.box(LARGURA, CORPO_Y, ALTURA, name="corpo").to_origin_corner()
    corpo.translate(0.0, PE_Y, 0.0)

    # bolsão: abre na ponta (+Y), teto em ALTURA e piso em VOID_Z_FLOOR
    vazio = prim.box(VOID_X, VOID_Y + 1.0, VOID_Z, name="bolsao").to_origin_corner()
    vazio.translate((LARGURA - VOID_X) / 2, COMPRIMENTO - VOID_Y, VOID_Z_FLOOR)
    peca = csg.subtract(corpo, vazio)

    # pé: aba lateral em Y = 0..3, centrada em X e em Z
    pe = prim.box(PE_X, PE_Y, PE_Z, name="pe").to_origin_corner()
    pe.translate((LARGURA - PE_X) / 2, 0.0, PE_Z0)
    peca = csg.union(peca, pe).renamed("extensor_braco_suporte_notebook_deitada")

    print(repr(peca))
    print("medidas:")
    for k, v in peca.stats().items():
        print(f"  {k:<14} {v:,.3f}" if isinstance(v, float) else f"  {k:<14} {v:,}")

    report = validate_mesh(peca)
    print()
    print(report.summary())
    print(f"  euler = {euler(peca)} (esperado 2: sem furo passante)")

    esperado = LARGURA * CORPO_Y * ALTURA - VOID_X * VOID_Y * VOID_Z + PE_X * PE_Y * PE_Z
    obtido = abs(peca.volume())
    erro = abs(obtido - esperado)
    desvio = erro / esperado * 100
    print()
    print(f"volume teórico = {esperado:.6f} mm3   obtido = {obtido:.6f} mm3   "
          f"erro = {erro:.2e} mm3 ({desvio:.8f}%)")

    if not report.ok or erro > 1e-3 or euler(peca) != 2:
        print("\nREPROVADO na validação - não vou exportar.")
        return 1
    print("(o kernel manifold3d é float32: sobra erro de ~1e-4 mm³ no volume, "
          "por isso a tolerância é 1e-3 mm³)")

    caminhos = [
        write_stl(peca, out / "extensor_braco_suporte_notebook_deitada.stl"),
        write_stl_ascii(peca, out / "extensor_braco_suporte_notebook_deitada_ascii.stl"),
        write_obj(peca, out / "extensor_braco_suporte_notebook_deitada.obj"),
    ]
    print("\ngerado:")
    for p in caminhos:
        print(f"  {p}  ({p.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
