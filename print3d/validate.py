"""Validação de malha: o que decide se o arquivo abre no slicer.

O STL não guarda índice de vértice compartilhado, então o slicer
reconstrói as arestas por coalescência de posição. Se sobrar qualquer
aresta com uma única face, o fatiador ou descarta a peça ou cria um buraco
no meio do caminho de extrusão, que é a causa mais comum de impressão
torta ou peça faltando fatia. Por isso o watertight é checado aqui,
antes de exportar.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .mesh import Mesh, vlen

TOL = 1e-9
ARESTA_MINIMA_IMPRESSIVEL = 0.05  # mm


@dataclass
class ValidationReport:
    n_vertices: int
    n_faces: int
    watertight: bool
    consistent_winding: bool
    positive_volume: bool
    n_boundary_edges: int
    n_nonmanifold_edges: int
    n_degenerate_faces: int
    min_edge_len: float
    signed_volume: float
    surface_area: float
    size_mm: tuple[float, float, float]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            self.watertight
            and self.consistent_winding
            and self.positive_volume
            and not self.errors
        )

    def summary(self) -> str:
        linhas = [
            f"validação: {'OK' if self.ok else 'FALHOU'}",
            f"  vértices = {self.n_vertices}   faces = {self.n_faces}",
            f"  tamanho  = {self.size_mm[0]:.2f} x {self.size_mm[1]:.2f} x "
            f"{self.size_mm[2]:.2f} mm",
            f"  volume   = {abs(self.signed_volume):.2f} mm3",
            f"  área     = {self.surface_area:.2f} mm2",
            f"  aresta mínima = {self.min_edge_len:.4f} mm",
            f"  fechada = {self.watertight}   winding ok = {self.consistent_winding}",
        ]
        linhas += [f"  ERRO: {e}" for e in self.errors]
        linhas += [f"  aviso: {w}" for w in self.warnings]
        return "\n".join(linhas)

    def __str__(self) -> str:  # pragma: no cover
        return self.summary()


def validate_mesh(mesh: Mesh) -> ValidationReport:
    """Checa malha fechada, orientação consistente e volume positivo."""
    errors: list[str] = []
    warnings: list[str] = []

    n_degenerate = 0
    min_edge = float("inf")
    edge_count: dict[tuple[int, int], int] = defaultdict(int)
    directed: dict[tuple[int, int], int] = defaultdict(int)

    for a, b, c in mesh.faces:
        pa, pb, pc = mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]
        e_ab = _dist(pa, pb)
        e_bc = _dist(pb, pc)
        e_ca = _dist(pc, pa)
        # degenerada = área zero: vértices coincidentes ou colineares
        area2 = _cross_len(
            (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]),
            (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]),
        )
        if min(e_ab, e_bc, e_ca) <= TOL or area2 <= TOL:
            n_degenerate += 1
            continue
        min_edge = min(min_edge, e_ab, e_bc, e_ca)
        for u, v in ((a, b), (b, c), (c, a)):
            edge_count[(u, v) if u < v else (v, u)] += 1
            directed[(u, v)] += 1

    boundary = sum(1 for n in edge_count.values() if n == 1)
    nonmanifold = sum(1 for n in edge_count.values() if n > 2)

    # Consistência de winding: em malha orientada cada aresta aparece uma
    # vez em cada sentido. Basta contar as arestas usadas num sentido só.
    winding_bad = sum(
        1 for (u, v) in directed if u < v and directed.get((v, u), 0) == 0
    )

    signed_vol = mesh.volume()
    watertight = boundary == 0 and nonmanifold == 0 and n_degenerate == 0
    positive = signed_vol > 0
    consistent = winding_bad == 0

    if boundary:
        errors.append(f"{boundary} aresta(s) de contorno - a peça não é fechada")
    if nonmanifold:
        errors.append(f"{nonmanifold} aresta(s) com mais de 2 faces")
    if n_degenerate:
        errors.append(f"{n_degenerate} face(s) degenerada(s) - vértices coincidentes")
    if not consistent:
        errors.append(
            "winding inconsistente - algumas normais apontam para dentro"
        )
    if signed_vol < 0:
        errors.append(
            f"volume negativo ({signed_vol:.2f} mm3) - normais invertidas; "
            "use Mesh.mirror() em vez de inverter vértices na mão"
        )
    if min_edge != float("inf") and min_edge < ARESTA_MINIMA_IMPRESSIVEL:
        warnings.append(
            f"aresta mínima de {min_edge:.4f} mm - abaixo do que um bico de "
            "0.4mm consegue imprimir de forma confiável"
        )

    return ValidationReport(
        n_vertices=mesh.n_vertices,
        n_faces=mesh.n_faces,
        watertight=watertight,
        consistent_winding=consistent,
        positive_volume=positive,
        n_boundary_edges=boundary,
        n_nonmanifold_edges=nonmanifold,
        n_degenerate_faces=n_degenerate,
        min_edge_len=0.0 if min_edge == float("inf") else min_edge,
        signed_volume=signed_vol,
        surface_area=mesh.area(),
        size_mm=mesh.size(),
        errors=errors,
        warnings=warnings,
    )


def _dist(p, q) -> float:
    return vlen((q[0] - p[0], q[1] - p[1], q[2] - p[2]))


def _cross_len(a, b) -> float:
    """Comprimento do produto vetorial = 2x a área do triângulo."""
    return vlen(
        (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )
    )


def merge_duplicate_vertices(mesh: Mesh, dist: float = 1e-6) -> Mesh:
    """Funde vértices coincidentes - passagem típica antes de exportar."""
    grid: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    out = Mesh(mesh.name)
    remap: dict[int, int] = {}
    for i, v in enumerate(mesh.vertices):
        key = (round(v[0] / dist), round(v[1] / dist), round(v[2] / dist))
        placed = None
        for cand in grid[key]:
            if _dist(out.vertices[cand], v) <= dist:
                placed = cand
                break
        if placed is None:
            placed = out.add_vertex(*v)
            grid[key].append(placed)
        remap[i] = placed
    for a, b, c in mesh.faces:
        na, nb, nc = remap[a], remap[b], remap[c]
        if len({na, nb, nc}) == 3:
            out.add_face(na, nb, nc)
    return out