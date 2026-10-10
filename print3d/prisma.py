"""Prisma por extrusão de polígono — para chanfro, nervura, rampa.

A biblioteca de primitivas só tinha formas retas (box, cylinder, lathe). Uma
parede inclinada (chanfro de 40°, nervura de reforço) precisa de um polígono
extrudado. O polígono pode ser côncavo (o caso da aba com chanfro: o vértice
onde o chanfro encontra a face de baixo da aba é reflexo), então a
triangulação é por orelhamento, não por leque.

Convenção de eixos: o polígono é dado no plano (y, z) e extrudado em X, de
``x0`` até ``x1``. O polígono é normalizado para anti-horário (área assinada
positiva) antes de triangular, e todas as faces saem com a normal para fora —
é o que a booleana do manifold3d exige.
"""

from __future__ import annotations

from .mesh import Mesh

EPS = 1e-9


def _area_assinada(poligono: list[tuple[float, float]]) -> float:
    s = 0.0
    n = len(poligono)
    for i in range(n):
        y1, z1 = poligono[i]
        y2, z2 = poligono[(i + 1) % n]
        s += y1 * z2 - y2 * z1
    return s / 2.0


def _ponto_em_triangulo(p, a, b, c) -> bool:
    """True se p está dentro (ou na borda) do triângulo a-b-c (anti-horário)."""
    def lado(u, v, w):
        return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])

    d1, d2, d3 = lado(a, b, p), lado(b, c, p), lado(c, a, p)
    return d1 >= -EPS and d2 >= -EPS and d3 >= -EPS


def _triangular(poligono: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    """Orelhamento: triangula polígono simples (convexo ou côncavo) anti-horário."""
    indices = list(range(len(poligono)))
    saida: list[tuple[int, int, int]] = []
    guarda = 0
    while len(indices) > 3 and guarda < 10000:
        guarda += 1
        for k in range(len(indices)):
            i = indices[k - 1]
            j = indices[k]
            m = indices[(k + 1) % len(indices)]
            a, b, c = poligono[i], poligono[j], poligono[m]
            cruz = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if cruz <= EPS:          # vértice reflexo ou colinear: não é orelha
                continue
            if any(_ponto_em_triangulo(poligono[t], a, b, c)
                   for t in indices if t not in (i, j, m)):
                continue             # tem vértice dentro: também não é orelha
            saida.append((i, j, m))
            indices.pop(k)
            break
        else:
            raise ValueError("polígono não é simples: orelhamento travou")
    if len(indices) == 3:
        saida.append((indices[0], indices[1], indices[2]))
    return saida


def extrude_polygon_yz(poligono: list[tuple[float, float]], x0: float, x1: float,
                       name: str = "prisma") -> Mesh:
    """Extruda o polígono do plano (y, z) de ``x0`` a ``x1`` em X."""
    if len(poligono) < 3:
        raise ValueError("polígono precisa de 3 vértices ou mais")
    if abs(x1 - x0) < EPS:
        raise ValueError("extrusão de espessura zero")

    poli = list(poligono)
    if _area_assinada(poli) < 0:     # normaliza para anti-horário
        poli.reverse()
    n = len(poli)

    m = Mesh(name)
    for y, z in poli:                # 0..n-1 na face x0
        m.add_vertex(x0, y, z)
    for y, z in poli:                # n..2n-1 na face x1
        m.add_vertex(x1, y, z)

    for a, b, c in _triangular(poli):
        m.add_face(a, c, b)                  # tampa em x0, normal -x
        m.add_face(n + a, n + b, n + c)      # tampa em x1, normal +x
    for i in range(n):                       # paredes
        j = (i + 1) % n
        m.add_quad(i, j, n + j, n + i)

    return m.renamed(name)
