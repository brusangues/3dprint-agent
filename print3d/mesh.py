"""Malha triangular: container de vértices e faces, com medida e transformações.

Convenção: faces são triplas de índices com ordenação anti-horária
(contra-clockwise) vista de fora, para que a normal aponte para o exterior.
Unidade padrão: milímetros (mm). O STL não guarda unidade, então o
slicer assume que o arquivo está em mm.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

Vec3 = tuple[float, float, float]
Tri = tuple[int, int, int]


# ---------------------------------------------------------------- vetores


def vadd(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vscale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def vdot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vlen(a: Vec3) -> float:
    return math.sqrt(vdot(a, a))


def face_normal(p0: Vec3, p1: Vec3, p2: Vec3) -> Vec3:
    """Normal geométrica (não normalizada) de um triângulo."""
    return vcross(vsub(p1, p0), vsub(p2, p0))


def normal_unit(p0: Vec3, p1: Vec3, p2: Vec3) -> Vec3:
    n = face_normal(p0, p1, p2)
    m = vlen(n)
    if m == 0.0:
        return (0.0, 0.0, 0.0)
    return (n[0] / m, n[1] / m, n[2] / m)


# ----------------------------------------------------------------- malha


class Mesh:
    """Malha triangular indexada."""

    __slots__ = ("name", "vertices", "faces")

    def __init__(
        self,
        name: str = "mesh",
        vertices: Iterable[Sequence[float]] | None = None,
        faces: Iterable[Sequence[int]] | None = None,
    ) -> None:
        self.name = name
        self.vertices: list[Vec3] = [
            (float(v[0]), float(v[1]), float(v[2])) for v in (vertices or [])
        ]
        self.faces: list[Tri] = [
            (int(f[0]), int(f[1]), int(f[2])) for f in (faces or [])
        ]

    # -------------------------------------------------- construção

    def add_vertex(self, x: float, y: float, z: float) -> int:
        self.vertices.append((float(x), float(y), float(z)))
        return len(self.vertices) - 1

    def add_face(self, a: int, b: int, c: int) -> None:
        self.faces.append((int(a), int(b), int(c)))

    def add_quad(self, a: int, b: int, c: int, d: int) -> None:
        """Quad (a,b,c,d) em ordem CCW vira dois triângulos."""
        self.add_face(a, b, c)
        self.add_face(a, c, d)

    def extend(self, other: "Mesh") -> "Mesh":
        """Anexa outra malha (sem fundir vértices)."""
        off = len(self.vertices)
        self.vertices.extend(other.vertices)
        self.faces.extend((a + off, b + off, c + off) for a, b, c in other.faces)
        return self

    def copy(self) -> "Mesh":
        return Mesh(self.name, list(self.vertices), list(self.faces))

    def renamed(self, name: str) -> "Mesh":
        self.name = name
        return self

    # ------------------------------------------------------ medidas

    @property
    def n_vertices(self) -> int:
        return len(self.vertices)

    @property
    def n_faces(self) -> int:
        return len(self.faces)

    def bbox_min(self) -> Vec3:
        if not self.vertices:
            return (0.0, 0.0, 0.0)
        return (
            min(v[0] for v in self.vertices),
            min(v[1] for v in self.vertices),
            min(v[2] for v in self.vertices),
        )

    def bbox_max(self) -> Vec3:
        if not self.vertices:
            return (0.0, 0.0, 0.0)
        return (
            max(v[0] for v in self.vertices),
            max(v[1] for v in self.vertices),
            max(v[2] for v in self.vertices),
        )

    def size(self) -> Vec3:
        lo, hi = self.bbox_min(), self.bbox_max()
        return (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])

    def centroid_bbox(self) -> Vec3:
        lo, hi = self.bbox_min(), self.bbox_max()
        return (
            (lo[0] + hi[0]) / 2.0,
            (lo[1] + hi[1]) / 2.0,
            (lo[2] + hi[2]) / 2.0,
        )

    def volume(self) -> float:
        """Volume assinado (mm^3) pelo método do tetraedro.

        Positivo quando as normais apontam para fora; use abs() se só
        precisar da medida.
        """
        total = 0.0
        for a, b, c in self.faces:
            p0, p1, p2 = self.vertices[a], self.vertices[b], self.vertices[c]
            total += vdot(p0, vcross(p1, p2))
        return total / 6.0

    def area(self) -> float:
        """Área total da superfície em mm^2."""
        total = 0.0
        for a, b, c in self.faces:
            total += vlen(face_normal(self.vertices[a], self.vertices[b], self.vertices[c]))
        return total / 2.0

    # ------------------------------------------------ transformações

    def translate(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> "Mesh":
        self.vertices = [(v[0] + dx, v[1] + dy, v[2] + dz) for v in self.vertices]
        return self

    def scale(self, sx: float = 1.0, sy: float | None = None, sz: float | None = None) -> "Mesh":
        sy = sx if sy is None else sy
        sz = sx if sz is None else sz
        if sx * sy * sz < 0:
            raise ValueError("escala espelhada inverte a orientação: use mirror()")
        self.vertices = [(v[0] * sx, v[1] * sy, v[2] * sz) for v in self.vertices]
        return self

    def rotate(self, axis: str = "z", degrees: float = 0.0) -> "Mesh":
        """Rotação de Rodrigues em torno de X, Y ou Z.

        v' = v*cos(t) + (u x v)*sen(t) + u*(u.v)*(1 - cos(t))
        O último termo precisa do produto escalar u.v: sem ele a matriz
        encolhe a peça e o volume não se preserva.
        """
        ax = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}[
            axis.lower()
        ]
        t = math.radians(degrees)
        c, s = math.cos(t), math.sin(t)
        ux, uy, uz = ax

        def rot(v: Vec3) -> Vec3:
            vx, vy, vz = v
            dot = ux * vx + uy * vy + uz * vz
            cx = uy * vz - uz * vy
            cy = uz * vx - ux * vz
            cz = ux * vy - uy * vx
            k = dot * (1.0 - c)
            return (
                vx * c + cx * s + ux * k,
                vy * c + cy * s + uy * k,
                vz * c + cz * s + uz * k,
            )

        self.vertices = [rot(v) for v in self.vertices]
        return self

    def mirror(self, axis: str = "x") -> "Mesh":
        """Espelha em X, Y ou Z invertendo a ordem das faces.

        Espelhar sem inverter faces deixa a normal para dentro e o
        volume negativo - o que reprova na hora de fatiar.
        """
        i = {"x": 0, "y": 1, "z": 2}[axis.lower()]
        self.vertices = [
            tuple(-v[i] if j == i else v[j] for j in range(3))  # type: ignore[misc]
            for v in self.vertices
        ]
        self.faces = [(a, c, b) for a, b, c in self.faces]
        return self

    def center_on_origin(self) -> "Mesh":
        cx, cy, cz = self.centroid_bbox()
        return self.translate(-cx, -cy, -cz)

    def move_to(self, x: float, y: float, z: float) -> "Mesh":
        """Desloca a peça para que o centro da bbox fique em (x, y, z)."""
        cx, cy, cz = self.centroid_bbox()
        return self.translate(x - cx, y - cy, z - cz)

    def to_origin_corner(self) -> "Mesh":
        """Desloca a peça para que o canto mínimo da bbox fique em (0,0,0)."""
        lo = self.bbox_min()
        return self.translate(-lo[0], -lo[1], -lo[2])

    # ------------------------------------------------------ relatório

    def stats(self) -> dict[str, float]:
        lo, hi = self.bbox_min(), self.bbox_max()
        return {
            "vértices": self.n_vertices,
            "faces": self.n_faces,
            "x (mm)": hi[0] - lo[0],
            "y (mm)": hi[1] - lo[1],
            "z (mm)": hi[2] - lo[2],
            "volume (mm3)": abs(self.volume()),
            "área (mm2)": self.area(),
        }

    def __repr__(self) -> str:
        sx, sy, sz = self.size()
        return (
            f"Mesh({self.name!r}, v={self.n_vertices}, f={self.n_faces}, "
            f"size={sx:.2f}x{sy:.2f}x{sz:.2f}mm)"
        )