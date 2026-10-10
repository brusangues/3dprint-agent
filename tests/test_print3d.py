"""Testes do framework print3d.

Rodar:  python -m pytest tests/ -q
ou sem pytest:  python tests/test_print3d.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from print3d import primitives as prim  # noqa: E402
from print3d.compound import box_with_pocket  # noqa: E402
from print3d.mesh import Mesh  # noqa: E402
from print3d.stl import read_stl, write_obj, write_stl, write_stl_ascii  # noqa: E402
from print3d.validate import merge_duplicate_vertices, validate_mesh  # noqa: E402

from print3d import csg  # noqa: E402

# Os testes de CSG exigem o kernel booleano. Sem ele, o resto da suíte
# continua rodando - por isso o skip em vez de import quebrado.
CSG = csg.csg_available()
requires_csg = pytest.mark.skipif(not CSG, reason="kernel booleano ausente (pip install trimesh manifold3d)")


def sem_csg(fn):
    """Mesma marca do pytest, mas o runner standalone entende.

    Sem isso, `python tests/test_print3d.py` reprovaria num ambiente sem
    o kernel, mesmo com os testes corretamente marcados para pular.
    """
    if not CSG:
        fn.__csg_skip__ = True
    return fn


TOL = 1e-6


def test_cube_volume_and_bbox():
    c = prim.cube(20.0)
    assert c.n_vertices == 8
    assert c.n_faces == 12
    assert abs(c.volume() - 8000.0) < 1e-6, c.volume()
    assert all(abs(x - 20.0) < TOL for x in c.size())


def test_cube_watertight_and_winding():
    r = validate_mesh(prim.cube(20.0))
    assert r.ok, r.summary()
    assert r.n_boundary_edges == 0
    assert r.n_nonmanifold_edges == 0
    assert r.signed_volume > 0


def test_cube_flat_face_flip_breaks_winding():
    m = prim.cube(20.0)
    m.faces[0] = m.faces[0][::-1]  # inverte a orientação de uma face
    r = validate_mesh(m)
    assert not r.ok
    assert any("winding" in e for e in r.errors)


def test_cube_missing_face_is_boundary():
    m = prim.cube(20.0)
    # remove os dois triângulos da face esquerda (índices 10 e 11)
    m.faces = [f for f in m.faces if f not in {(3, 0, 4), (3, 4, 7)}]
    r = validate_mesh(m)
    assert not r.watertight
    # a face forma um quadrado: ficam 4 arestas de contorno
    assert r.n_boundary_edges == 4, r.n_boundary_edges


def test_mirror_keeps_valid():
    m = prim.cube(20.0).mirror("x")
    r = validate_mesh(m)
    assert r.ok, r.summary()
    assert r.signed_volume > 0


def test_cylinder():
    c = prim.cylinder(10.0, 20.0, segments=64)
    esperado = 3.141592653589793 * 100.0 * 20.0
    assert abs(abs(c.volume()) - esperado) / esperado < 5e-3, c.volume()
    assert validate_mesh(c).ok, validate_mesh(c).summary()


def test_sphere():
    s = prim.sphere(10.0, segments=48, rings=24)
    esperado = 4.0 / 3.0 * 3.141592653589793 * 1000.0
    # a esfera UV aproxima por um poliedro inscrito, então o volume fica
    # sempre um pouco abaixo do ideal - erro de ~0.7% nesta resolução
    assert abs(abs(s.volume()) - esperado) / esperado < 2e-2, s.volume()
    assert validate_mesh(s).ok, validate_mesh(s).summary()


def test_washer_has_hole_and_is_closed():
    w = prim.washer(outer_radius=10.0, inner_radius=5.0, height=2.0)
    r = validate_mesh(w)
    assert r.ok, r.summary()
    esperado = 3.141592653589793 * (100.0 - 25.0) * 2.0
    assert abs(abs(w.volume()) - esperado) / esperado < 5e-3, w.volume()


def test_frustum_cone():
    k = prim.frustum(0.0, 10.0, 20.0, segments=64)
    esperado = (1.0 / 3.0) * 3.141592653589793 * 100.0 * 20.0
    assert abs(abs(k.volume()) - esperado) / esperado < 5e-3, k.volume()
    assert validate_mesh(k).ok, validate_mesh(k).summary()


def test_transformations_preserve_validity():
    c = prim.cube(20.0).rotate("z", 37.0).rotate("y", 12.0).translate(5, -3, 8)
    assert validate_mesh(c).ok, validate_mesh(c).summary()
    assert abs(abs(c.volume()) - 8000.0) < 1e-3


def test_move_to_and_origin_corner():
    c = prim.cube(20.0).to_origin_corner()
    assert max(abs(v) for v in c.bbox_min()) < TOL
    assert all(abs(x - 20.0) < TOL for x in c.size())


def test_stl_roundtrip_binary(tmp=None):
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "c.stl"
        write_stl(prim.cube(20.0), p)
        raw = p.read_bytes()
        assert raw[:5] == b"solid" or True  # header é texto livre
        n = struct.unpack("<I", raw[80:84])[0]
        assert n == 12
        assert len(raw) == 84 + 12 * 50
        back = read_stl(p)
        assert abs(abs(back.volume()) - 8000.0) < 1e-3
        assert validate_mesh(back).ok, validate_mesh(back).summary()


def test_stl_roundtrip_ascii():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "c.stl"
        write_stl_ascii(prim.cube(20.0), p)
        back = read_stl(p)
        assert back.n_faces == 12
        assert abs(abs(back.volume()) - 8000.0) < 1e-3


def test_obj_written():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = write_obj(prim.cube(20.0), Path(td) / "c.obj")
        text = p.read_text(encoding="utf-8")
        assert text.count("\nv ") == 8
        assert text.count("\nf ") == 12


def test_merge_duplicate_vertices():
    m = Mesh("dup", [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 0, 0)], [(0, 1, 2), (3, 1, 2)])
    merged = merge_duplicate_vertices(m)
    assert merged.n_vertices == 3
    # a face (3,1,2) colapsa para vértices repetidos e é descartada
    assert merged.n_faces == 1


def test_degenerate_face_detected():
    m = Mesh("deg", [(0, 0, 0), (1, 0, 0), (2, 0, 0)], [(0, 1, 2)])
    r = validate_mesh(m)
    assert not r.ok
    assert r.n_degenerate_faces == 1


def test_pocket_volume_exact():
    p = box_with_pocket(16, 10, 40, 4, 4, 10)
    esperado = 16 * 10 * 40 - 4 * 4 * 10
    assert abs(abs(p.volume()) - esperado) < 1e-9, p.volume()


def test_pocket_is_watertight():
    p = box_with_pocket(16, 10, 40, 4, 4, 10)
    r = validate_mesh(p)
    assert r.ok, r.summary()
    assert r.n_boundary_edges == 0
    assert r.signed_volume > 0


def test_pocket_geometry():
    p = box_with_pocket(16, 10, 40, 4, 4, 10)
    assert all(abs(x - 16) < TOL for x in (p.size()[0],))
    assert abs(p.size()[1] - 10) < TOL
    assert abs(p.size()[2] - 40) < TOL
    assert p.bbox_min() == (0.0, 0.0, 0.0)


def test_pocket_rejects_bad_args():
    for args in (
        (16, 10, 40, 20, 4, 10),   # cavidade maior que a base
        (16, 10, 40, 4, 4, 50),    # cavidade mais alta que a peça
        (16, 10, 40, 0, 4, 10),    # cavidade de largura zero
        (-1, 10, 40, 4, 4, 10),    # dimensão negativa
    ):
        try:
            box_with_pocket(*args)
        except ValueError:
            continue
        raise AssertionError(f"deveria ter rejeitado {args}")


def test_pocket_stl_roundtrip():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "p.stl"
        write_stl(box_with_pocket(16, 10, 40, 4, 4, 10), p)
        back = read_stl(p)
        assert abs(abs(back.volume()) - 6240.0) < 1e-6, back.volume()
        assert validate_mesh(back).ok, validate_mesh(back).summary()


# ------------------------------------------------------------------ CSG


@sem_csg
def test_subtract_pocket_exact():
    """A operação que reprovou o BSP: furo quadrado atravessando o topo.

    O BSP dava volume certo mas area do topo errada e casca aberta.
    Aqui conferimos os tres: volume, area da placa e fechamento.
    """
    import numpy as np

    a = prim.box(20, 20, 20).to_origin_corner()
    b = prim.box(5, 15, 15).to_origin_corner().translate(7.5, 7.5, 5)
    r = csg.subtract(a, b)

    # volume: 8000 - 5*12.5*15 = 7062.5
    assert abs(abs(r.volume()) - 7062.5) < 1e-6, r.volume()

    rep = validate_mesh(r)
    assert rep.ok, rep.summary()
    assert rep.n_boundary_edges == 0


@sem_csg
def test_subtract_areas_of_each_plate():
    """Cada plano da peça tem a área exatamente esperada."""
    import numpy as np

    a = prim.box(20, 20, 20).to_origin_corner()
    b = prim.box(5, 15, 15).to_origin_corner().translate(7.5, 7.5, 5)
    r = csg.subtract(a, b)

    v = np.array(r.vertices)
    f = np.array(r.faces)

    def area_no_plano(z):
        mask = np.all(np.abs(v[f, 2] - z) < 1e-6, axis=1)
        idx = set(np.where(mask)[0].tolist())
        total = 0.0
        for i, tri in enumerate(r.faces):
            if i in idx:
                p0, p1, p2 = (r.vertices[t] for t in tri)
                u = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
                w = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
                cr = (
                    u[1] * w[2] - u[2] * w[1],
                    u[2] * w[0] - u[0] * w[2],
                    u[0] * w[1] - u[1] * w[0],
                )
                total += (cr[0] ** 2 + cr[1] ** 2 + cr[2] ** 2) ** 0.5 / 2.0
        return total

    # fundo cheio: 20x20 = 400
    assert abs(area_no_plano(0.0) - 400.0) < 1e-6, area_no_plano(0.0)
    # topo: 400 menos a fatia do furo que atravessa (5 x 12.5) = 337.5
    assert abs(area_no_plano(20.0) - 337.5) < 1e-6, area_no_plano(20.0)


@sem_csg
def test_union_and_intersect():
    a = prim.box(20, 20, 20).to_origin_corner()
    b = prim.box(20, 20, 20).to_origin_corner().translate(10, 10, 10)

    u = csg.union(a, b)
    assert abs(abs(u.volume()) - (8000.0 + 8000.0 - 1000.0)) < 1e-6, u.volume()
    assert validate_mesh(u).ok, validate_mesh(u).summary()

    i = csg.intersect(a, b)
    assert abs(abs(i.volume()) - 1000.0) < 1e-6, i.volume()
    assert validate_mesh(i).ok, validate_mesh(i).summary()


@sem_csg
def test_subtract_through_hole():
    """Furo passante circular: o volume bate com pi*r^2*h."""
    import math

    a = prim.box(30, 30, 10).to_origin_corner()
    cil = prim.cylinder(4.0, 40.0, segments=128, centered=True).translate(15, 15, 5)
    r = csg.subtract(a, cil)
    esperado = 30 * 30 * 10 - math.pi * 16 * 10
    # o cilindro de 128 lados faz area um pouco menor que o circulo
    assert abs(abs(r.volume()) - esperado) / esperado < 1e-4, r.volume()
    assert validate_mesh(r).ok, validate_mesh(r).summary()


@sem_csg
def test_subtract_matches_compound():
    """CSG e a construção direta precisam dar a mesma peça.

    Se divergirem, uma das duas caminhos tem bug - e como as duas são
    independentes, comparar as duas é o teste mais forte que existe
    para a geometria da cavidade.
    """
    via_csg = csg.subtract(
        prim.box(16, 10, 40).to_origin_corner(),
        prim.box(4, 4, 10).to_origin_corner().translate(6, 3, 30),
    )
    direta = box_with_pocket(16, 10, 40, 4, 4, 10)
    assert abs(abs(via_csg.volume()) - abs(direta.volume())) < 1e-6
    assert validate_mesh(via_csg).ok


def _run_standalone() -> int:
    """Roda todos os testes sem depender do pytest."""
    import inspect
    import tempfile

    falhas = 0
    pulados = 0
    for nome, fn in sorted(globals().items()):
        if not nome.startswith("test_") or not callable(fn):
            continue
        if getattr(fn, "__csg_skip__", False):
            pulados += 1
            print(f"pulado  {nome} (kernel booleano ausente)")
            continue
        try:
            if "tmp" in inspect.signature(fn).parameters:
                with tempfile.TemporaryDirectory() as td:
                    fn(Path(td))
            else:
                fn()
        except Exception as exc:  # noqa: BLE001
            falhas += 1
            print(f"FALHOU {nome}: {exc}")
        else:
            print(f"ok     {nome}")
    print(f"\n{falhas} falha(s), {pulados} pulado(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())