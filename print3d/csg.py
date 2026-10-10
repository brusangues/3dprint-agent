"""CSG - união, subtração e interseção via manifold3d (kernel real).

O backend é o Manifold, um kernel de geometria robusta usado no
jogo e no CAD leve. Diferente do algoritmo BSP popular (csg.js), ele
mantém a topologia exata: a casca fecha, o número de Euler dá 2 e o
volume bate com a fórmula analítica no dígito.

Quando manifold3d não está instalado, `csg_available()` devolve False e
o framework continua funcionando - as primitivas de `compound.py`
constroem as peças compound sem booleana, então nenhum script quebra.
"""

from __future__ import annotations

from .mesh import Mesh

try:  # pragma: no cover - depende do ambiente
    import trimesh
    from trimesh import boolean as _tm_boolean

    CSG_DISPONIVEL = True
    MOTIVO_INDISPONIVEL = ""
except ImportError as exc:  # pragma: no cover
    trimesh = None
    _tm_boolean = None
    CSG_DISPONIVEL = False
    MOTIVO_INDISPONIVEL = str(exc)


def csg_available() -> bool:
    """True se o kernel booleano está disponível."""
    return CSG_DISPONIVEL


def _para_trimesh(mesh: Mesh):
    """Mesh -> trimesh.Trimesh, preservando unidades (mm)."""
    return trimesh.Trimesh(
        vertices=mesh.vertices,
        faces=mesh.faces,
        process=False,
        validate=False,
    )


def _para_print3d(tm, name: str) -> Mesh:
    """trimesh.Trimesh -> Mesh, funde vértices e normaliza normais."""
    from .validate import merge_duplicate_vertices

    m = Mesh(name, tm.vertices.tolist(), tm.faces.tolist())
    m = merge_duplicate_vertices(m, dist=1e-7)
    if m.volume() < 0:  # normal invertida: espelha a malha inteira
        m.mirror("x")
    return m.renamed(name)


def union(a: Mesh, b: Mesh) -> Mesh:
    """A + B: junta os volumes."""
    _exigir_kernel()
    r = _tm_boolean.union([_para_trimesh(a), _para_trimesh(b)])
    return _para_print3d(r, f"{a.name}_mais_{b.name}")


def subtract(a: Mesh, b: Mesh) -> Mesh:
    """A - B: remove de ``a`` o volume de ``b``."""
    _exigir_kernel()
    r = _tm_boolean.difference([_para_trimesh(a), _para_trimesh(b)])
    return _para_print3d(r, f"{a.name}_menos_{b.name}")


def intersect(a: Mesh, b: Mesh) -> Mesh:
    """A ∩ B: volume comum."""
    _exigir_kernel()
    r = _tm_boolean.intersection([_para_trimesh(a), _para_trimesh(b)])
    return _para_print3d(r, f"{a.name}_int_{b.name}")


def _exigir_kernel() -> None:
    if not CSG_DISPONIVEL:
        raise RuntimeError(
            "CSG precisa do kernel booleano. Instale com:\n"
            "    pip install trimesh manifold3d\n"
            f"Detalhe: {MOTIVO_INDISPONIVEL}"
        )


# ------------------------------------------------------------- açúcar


def difference(a: Mesh, b: Mesh) -> Mesh:
    """Alias de :func:`subtract`, para quem já conhece o nome do trimesh."""
    return subtract(a, b)