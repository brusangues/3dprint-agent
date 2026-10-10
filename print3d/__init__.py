"""
print3d - modelagem de peças para impressão 3D em Python puro.

Escreve STL (binário/ASCII) e OBJ a partir de uma malha triangular,
valida se a malha é fechada (watertight) e gera preview PNG.

Sem dependências obrigatórias: só a biblioteca padrão.
matplotlib é usado apenas para o preview (opcional).
"""

from .mesh import Mesh, Vec3
from . import primitives as prim
from .compound import box_with_pocket
from .csg import union, subtract, intersect, csg_available
from .validate import validate_mesh, ValidationReport
from .stl import write_stl, write_stl_ascii, read_stl, write_obj

__all__ = [
    "Mesh",
    "Vec3",
    "prim",
    "box_with_pocket",
    "union",
    "subtract",
    "intersect",
    "csg_available",
    "validate_mesh",
    "ValidationReport",
    "write_stl",
    "write_stl_ascii",
    "read_stl",
    "write_obj",
]

__version__ = "0.3.0"