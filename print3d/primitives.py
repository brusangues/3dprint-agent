"""Primitivas paramétricas (todas fechadas por padrão, em mm)."""

from __future__ import annotations

import math

from .mesh import Mesh

TAU = 2.0 * math.pi


# ------------------------------------------------------------------- cubo


def box(
    width: float = 20.0,
    depth: float = 20.0,
    height: float = 20.0,
    name: str = "caixa",
    centered: bool = True,
) -> Mesh:
    """Caixa retangular (cubo quando width=depth=height).

    ``centered=True`` põe o centro da peça na origem, convenção usada pelo
    Blender e pelo Cura. Para a peça "sentar" na mesa em z=0, chame
    ``to_origin_corner()`` ou ``move_to(0, 0, 0)``.
    """
    w, d, h = float(width), float(depth), float(height)
    if min(w, d, h) <= 0:
        raise ValueError("largura, profundidade e altura precisam ser > 0")
    ox = -w / 2.0 if centered else 0.0
    oy = -d / 2.0 if centered else 0.0
    oz = -h / 2.0 if centered else 0.0
    m = Mesh(name)
    m.vertices = [
        (ox, oy, oz),               # 0
        (ox + w, oy, oz),           # 1
        (ox + w, oy + d, oz),       # 2
        (ox, oy + d, oz),           # 3
        (ox, oy, oz + h),           # 4
        (ox + w, oy, oz + h),       # 5
        (ox + w, oy + d, oz + h),   # 6
        (ox, oy + d, oz + h),       # 7
    ]
    # faces em sentido anti-horário visto de fora
    m.faces = [
        (0, 3, 2), (0, 2, 1),        # base, normal -z
        (4, 5, 6), (4, 6, 7),        # topo, normal +z
        (0, 1, 5), (0, 5, 4),        # frente, normal -y
        (1, 2, 6), (1, 6, 5),        # direita, normal +x
        (2, 3, 7), (2, 7, 6),        # fundo, normal +y
        (3, 0, 4), (3, 4, 7),        # esquerda, normal -x
    ]
    return m


def cube(size: float = 20.0, name: str = "cubo", centered: bool = True) -> Mesh:
    """Cubo de aresta ``size`` mm."""
    return box(size, size, size, name=name, centered=centered)


# ---------------------------------------------------------------- cilindro


def cylinder(
    radius: float = 10.0,
    height: float = 20.0,
    segments: int = 64,
    name: str = "cilindro",
    centered: bool = True,
    caps: bool = True,
) -> Mesh:
    """Cilindro com tampa opcional."""
    if radius <= 0 or height <= 0:
        raise ValueError("raio e altura precisam ser > 0")
    if segments < 3:
        raise ValueError("segments >= 3")
    z0 = -height / 2.0 if centered else 0.0
    m = Mesh(name)
    for z in (z0, z0 + height):
        for i in range(segments):
            a = TAU * i / segments
            m.add_vertex(radius * math.cos(a), radius * math.sin(a), z)
    c_bot = m.add_vertex(0.0, 0.0, z0) if caps else -1
    c_top = m.add_vertex(0.0, 0.0, z0 + height) if caps else -1
    for i in range(segments):
        j = (i + 1) % segments
        m.add_quad(i, j, segments + j, segments + i)
        if caps:
            m.add_face(c_bot, j, i)
            m.add_face(c_top, segments + i, segments + j)
    return m


def frustum(
    radius_bottom: float = 10.0,
    radius_top: float = 5.0,
    height: float = 20.0,
    segments: int = 64,
    name: str = "frustum",
    centered: bool = True,
    caps: bool = True,
) -> Mesh:
    """Cone (raio 0) ou tronco de cone."""
    if height <= 0 or radius_bottom < 0 or radius_top < 0:
        raise ValueError("altura > 0 e raios >= 0")
    if max(radius_bottom, radius_top) <= 0:
        raise ValueError("pelo menos um raio > 0")
    z0 = -height / 2.0 if centered else 0.0
    m = Mesh(name)

    def ring(r: float, z: float) -> list[int]:
        """Anel de vértices; r == 0 vira um pólo com índice único."""
        if r <= 0:
            return [m.add_vertex(0.0, 0.0, z)] * segments
        return [
            m.add_vertex(
                r * math.cos(TAU * i / segments), r * math.sin(TAU * i / segments), z
            )
            for i in range(segments)
        ]

    bot = ring(radius_bottom, z0)
    top = ring(radius_top, z0 + height)
    bot_pole = radius_bottom <= 0
    top_pole = radius_top <= 0
    for i in range(segments):
        j = (i + 1) % segments
        if bot_pole and top_pole:
            continue  # cilindro de altura zero: nada a fazer
        if bot_pole:
            m.add_face(bot[i], top[j], top[i])       # leque saindo do pólo
        elif top_pole:
            m.add_face(bot[i], bot[j], top[i])       # leque entrando no pólo
        else:
            m.add_quad(bot[i], bot[j], top[j], top[i])
    if caps:
        if radius_bottom > 0:
            c = m.add_vertex(0.0, 0.0, z0)
            for i in range(segments):
                m.add_face(c, bot[(i + 1) % segments], bot[i])
        if radius_top > 0:
            c = m.add_vertex(0.0, 0.0, z0 + height)
            for i in range(segments):
                m.add_face(c, top[i], top[(i + 1) % segments])
    return m


# ------------------------------------------------------------------ esfera


def sphere(
    radius: float = 10.0,
    segments: int = 48,
    rings: int = 24,
    name: str = "esfera",
    centered: bool = True,
) -> Mesh:
    """Esfera UV. Os polos são vértices únicos, sem triângulos degenerados."""
    if radius <= 0:
        raise ValueError("raio > 0")
    if segments < 3 or rings < 2:
        raise ValueError("segments >= 3 e rings >= 2")
    z0 = -radius if centered else 0.0
    m = Mesh(name)
    top = m.add_vertex(0.0, 0.0, z0 + 2.0 * radius)
    grid: list[list[int]] = []
    for r in range(1, rings):
        phi = math.pi * r / rings
        z = z0 + radius + radius * math.cos(phi)
        rr = radius * math.sin(phi)
        grid.append(
            [
                m.add_vertex(
                    rr * math.cos(TAU * i / segments),
                    rr * math.sin(TAU * i / segments),
                    z,
                )
                for i in range(segments)
            ]
        )
    bottom = m.add_vertex(0.0, 0.0, z0)
    for i in range(segments):
        j = (i + 1) % segments
        m.add_face(top, grid[0][i], grid[0][j])
        m.add_face(bottom, grid[-1][j], grid[-1][i])
    for r in range(len(grid) - 1):
        for i in range(segments):
            j = (i + 1) % segments
            # grid[r] está acima de grid[r+1]: a ordem do quad é a que
            # mantém a normal para fora, com o anel de cima como "base".
            m.add_quad(grid[r][i], grid[r + 1][i], grid[r + 1][j], grid[r][j])
    return m


# -------------------------------------------------------------------- anel


def washer(
    outer_radius: float = 10.0,
    inner_radius: float = 5.0,
    height: float = 2.0,
    segments: int = 64,
    name: str = "anel",
) -> Mesh:
    """Anel/arruela - exemplo de peça com furo through.

    Construída por revolução: um perfil (r, z) de 4 pontos descreve a
    seção da peça, e o furo é só a continuação do perfil. É o mesmo
    mecanismo do cone, e evita o problema de "colar dois cilindros e torcer
    as faces", que produz malha não-manifold.
    """
    if not 0 < inner_radius < outer_radius:
        raise ValueError("exige 0 < raio_interno < raio_externo")
    if height <= 0:
        raise ValueError("altura > 0")

    # perfil fechado no plano (r, z), anti-horário: externo embaixo -> sobe
    perfil = [
        (inner_radius, 0.0),          # dentro, base
        (outer_radius, 0.0),          # fora, base
        (outer_radius, height),       # fora, topo
        (inner_radius, height),       # dentro, topo
    ]
    return lathe(perfil, segments=segments, name=name)


def lathe(
    perfil: list[tuple[float, float]],
    segments: int = 64,
    name: str = "revolucao",
    close_ends: bool = True,
) -> Mesh:
    """Sólido de revolução em torno do eixo Z a partir de um perfil (r, z).

    O perfil é uma polilinha fechada em (r, z). Pontos com r=0 viram o
    eixo (pólo) e geram vértice único. É a primitiva que resolve anéis,
    """
    if len(perfil) < 3:
        raise ValueError("perfil precisa de pelo menos 3 pontos")
    if any(r < 0 for r, _ in perfil):
        raise ValueError("raio negativo no perfil")
    m = Mesh(name)

    # cada ponto do perfil gera um anel (ou um vértice único se r == 0)
    aneis: list[list[int]] = []
    for r, z in perfil:
        if r == 0:
            aneis.append([m.add_vertex(0.0, 0.0, z)] * segments)
        else:
            aneis.append(
                [
                    m.add_vertex(
                        r * math.cos(TAU * i / segments),
                        r * math.sin(TAU * i / segments),
                        z,
                    )
                    for i in range(segments)
                ]
            )

    n = len(aneis)
    pares = [(k, (k + 1) % n) for k in range(n if close_ends else n - 1)]
    for k, k2 in pares:
        a, b = aneis[k], aneis[k2]
        for i in range(segments):
            j = (i + 1) % segments
            if a[i] == a[j] and b[i] == b[j] == a[i]:
                continue
            if a[i] == b[i]:  # pólo na base da faixa
                m.add_face(a[i], b[j], b[i])
            elif b[i] == b[j]:  # pólo no topo da faixa
                m.add_face(a[i], a[j], b[i])
            else:
                m.add_quad(a[i], a[j], b[j], b[i])
    return m