"""Escrita e leitura de STL (binário e ASCII) e OBJ.

O STL é o formato mais permissivo que existe: guarda só triângulos, sem
índice de vértice compartilhado, sem informação de peça, sem unidade. Por
isso a checagem de qualidade precisa acontecer antes, no write_stl().
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterator

from .mesh import Mesh, Vec3, normal_unit


def _triangles(mesh: Mesh) -> Iterator[tuple[Vec3, Vec3, Vec3]]:
    for a, b, c in mesh.faces:
        yield mesh.vertices[a], mesh.vertices[b], mesh.vertices[c]


# ------------------------------------------------------------ STL binário


def write_stl(mesh: Mesh, path: str | Path, header: str | None = None) -> Path:
    """Grava STL binário (compacto, padrão de todo slicer)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (header or f"print3d {mesh.name}")[:79]

    n = mesh.n_faces
    with path.open("wb") as fh:
        # 80 bytes de cabeçalho + uint32 com a contagem de triângulos
        fh.write(text.encode("ascii", "replace").ljust(80, b"\0"))
        fh.write(struct.pack("<I", n))
        for p0, p1, p2 in _triangles(mesh):
            fh.write(struct.pack("<3f", *normal_unit(p0, p1, p2)))
            fh.write(struct.pack("<9f", *p0, *p1, *p2))
            fh.write(struct.pack("<H", 0))  # contador de atributos
    return path


# -------------------------------------------------------------- STL ASCII


def write_stl_ascii(mesh: Mesh, path: str | Path, name: str | None = None) -> Path:
    """Grava STL em texto - útil para diff e inspeção manual."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    solid = name or mesh.name
    lines = [f"solid {solid}"]
    for p0, p1, p2 in _triangles(mesh):
        n = normal_unit(p0, p1, p2)
        lines.append(f"  facet normal {n[0]:.6e} {n[1]:.6e} {n[2]:.6e}")
        lines.append("    outer loop")
        for p in (p0, p1, p2):
            lines.append(f"      vertex {p[0]:.6e} {p[1]:.6e} {p[2]:.6e}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append(f"endsolid {solid}")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


# ------------------------------------------------------------------ leitura


def read_stl(path: str | Path) -> Mesh:
    """Lê STL binário ou ASCII, fundindo vértices coincidentes."""
    path = Path(path)
    raw = path.read_bytes()
    if _looks_binary(raw):
        return _read_binary(path, raw)
    return _read_ascii(path)


def _looks_binary(raw: bytes) -> bool:
    if len(raw) < 84:
        return True
    if not raw[:5].lower().startswith(b"solid"):
        return True
    n = struct.unpack("<I", raw[80:84])[0]
    return len(raw) == 84 + n * 50


def _read_binary(path: Path, raw: bytes) -> Mesh:
    n = struct.unpack("<I", raw[80:84])[0]
    m = Mesh(path.stem)
    index: dict[Vec3, int] = {}

    def vid(p: Vec3) -> int:
        key = (round(p[0], 5), round(p[1], 5), round(p[2], 5))
        if key not in index:
            index[key] = m.add_vertex(*key)
        return index[key]

    for k in range(n):
        off = 84 + k * 50
        vals = struct.unpack("<12fH", raw[off : off + 50])
        m.add_face(vid(vals[3:6]), vid(vals[6:9]), vid(vals[9:12]))
    return m


def _read_ascii(path: Path) -> Mesh:
    m = Mesh(path.stem)
    index: dict[Vec3, int] = {}
    pending: list[int] = []
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        t = line.split()
        if len(t) == 4 and t[0] == "vertex":
            p = (round(float(t[1]), 5), round(float(t[2]), 5), round(float(t[3]), 5))
            if p not in index:
                index[p] = m.add_vertex(*p)
            pending.append(index[p])
            if len(pending) == 3:
                m.add_face(*pending)
                pending = []
    return m


# ---------------------------------------------------------------------- OBJ


def write_obj(mesh: Mesh, path: str | Path) -> Path:
    """Grava OBJ - formato com vértices compartilhados, útil para editar."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = [f"# {mesh.name} - gerado por print3d", f"o {mesh.name}"]
    out += [f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}" for v in mesh.vertices]
    out += [f"f {a+1} {b+1} {c+1}" for a, b, c in mesh.faces]  # OBJ é 1-indexado
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path