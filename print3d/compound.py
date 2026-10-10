"""Peças compound: caixa com cavidade reta.

Construída vértice por vértice, sem depender de booleanas. É o caminho
exato para a maioria das peças de impressão 3D e tem duas vantagens
sobre subtract: o volume bate no dígito e não sobra triangulação
ascidental.

Se um dia for preciso combinar volumes de forma arbitrária (união de
dois cilindros cruzados, chanfro curvo, interseção parcial), aí sim vale
instalar um kernel booleano de verdade - trimesh com manifold3d, ou
OpenSCAD. O README explica a troca.
"""

from __future__ import annotations

from .mesh import Mesh


def box_with_pocket(
    width: float,
    depth: float,
    height: float,
    pocket_width: float,
    pocket_depth: float,
    pocket_height: float,
    name: str = "peca",
) -> Mesh:
    """Caixa com cavidade reta (um "pocket") aberta pelo topo.

    A cavidade é centralizada em x e y e vai de z = height - pocket_height
    até z = height. Todos os parâmetros em mm.

    A casca tem 16 faces: base, 4 paredes externas, 4 trapézios de topo,
    4 paredes internas e o fundo da cavidade.
    """
    for campo, v in (
        ("width", width),
        ("depth", depth),
        ("height", height),
        ("pocket_width", pocket_width),
        ("pocket_depth", pocket_depth),
        ("pocket_height", pocket_height),
    ):
        if v <= 0:
            raise ValueError(f"{campo} precisa ser > 0")
    if not (0 < pocket_width < width and 0 < pocket_depth < depth):
        raise ValueError("a cavidade precisa ser menor que a base")
    if not (0 < pocket_height < height):
        raise ValueError("a cavidade precisa ser mais baixa que a peça")

    x1, y1, z1 = width, depth, height
    cx0 = (width - pocket_width) / 2.0
    cy0 = (depth - pocket_depth) / 2.0
    cx1 = cx0 + pocket_width
    cy1 = cy0 + pocket_depth
    fz = height - pocket_height

    m = Mesh(name)
    # base
    m.add_vertex(0.0, 0.0, 0.0)   # 0
    m.add_vertex(x1, 0.0, 0.0)   # 1
    m.add_vertex(x1, y1, 0.0)   # 2
    m.add_vertex(0.0, y1, 0.0)   # 3
    # topo externo
    m.add_vertex(0.0, 0.0, z1)   # 4
    m.add_vertex(x1, 0.0, z1)   # 5
    m.add_vertex(x1, y1, z1)   # 6
    m.add_vertex(0.0, y1, z1)   # 7
    # boca da cavidade no topo
    m.add_vertex(cx0, cy0, z1)  # 8
    m.add_vertex(cx1, cy0, z1)  # 9
    m.add_vertex(cx1, cy1, z1)  # 10
    m.add_vertex(cx0, cy1, z1)  # 11
    # fundo da cavidade
    m.add_vertex(cx0, cy0, fz)  # 12
    m.add_vertex(cx1, cy0, fz)  # 13
    m.add_vertex(cx1, cy1, fz)  # 14
    m.add_vertex(cx0, cy1, fz)  # 15

    # base: normal -z
    m.add_quad(0, 3, 2, 1)
    # paredes externas: normais para fora
    m.add_quad(0, 1, 5, 4)   # frente, -y
    m.add_quad(1, 2, 6, 5)   # direita, +x
    m.add_quad(2, 3, 7, 6)   # fundo, +y
    m.add_quad(3, 0, 4, 7)   # esquerda, -x
    # topo: anel entre a borda externa e a boca da cavidade, em 4 trapézios
    m.add_quad(4, 5, 9, 8)
    m.add_quad(5, 6, 10, 9)
    m.add_quad(6, 7, 11, 10)
    m.add_quad(7, 4, 8, 11)
    # paredes internas: normal para o centro da cavidade
    m.add_quad(8, 9, 13, 12)  # frente
    m.add_quad(9, 10, 14, 13)  # direita
    m.add_quad(10, 11, 15, 14)  # fundo
    m.add_quad(11, 8, 12, 15)  # esquerda
    # fundo da cavidade: olhando de dentro para cima, normal +z
    m.add_quad(12, 13, 14, 15)
    return m