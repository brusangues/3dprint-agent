"""Fatia um STL com o CuraEngine usando os perfis reais da instalacao do Cura.

Monta a pilha de containers do Cura (user > quality_changes > intent > quality
> material > variant > definition_changes > definition), resolve primeiro-vence
e passa o resultado para o CuraEngine via -s. O CuraEngine preenche o resto com
os defaults das definicoes (-j), exatamente como o Cura faz na GUI.

Uso:
    python tools/slice_cura.py --stl out/placa_com_furos.stl --profile low ^
        --out out/placa_com_furos_low2026.gcode [--no-user]
"""

from __future__ import annotations

import argparse
import configparser
import json
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CURA_APP = Path("C:/Program Files/UltiMaker Cura 5.13.0")
CURA_ENGINE = CURA_APP / "CuraEngine.exe"
RES = CURA_APP / "share/cura/resources"
CURA_USER = Path.home() / "AppData/Roaming/cura/5.13"

MACHINE = "Creality Ender-3 Pro default"
EXTRUDER = "creality_base_extruder_0 #2"

# nome no XML do material -> chave interna do Cura (XmlMaterialProfile.py)
MATERIAL_MAP = {
    "print temperature": "default_material_print_temperature",
    "heated bed temperature": "default_material_bed_temperature",
    "standby temperature": "material_standby_temperature",
    "print cooling": "cool_fan_speed",
    "retraction amount": "retraction_amount",
    "retraction speed": "retraction_speed",
    "adhesion tendency": "material_adhesion_tendency",
    "surface energy": "material_surface_energy",
    "build volume temperature": "build_volume_temperature",
}

# a temperatura efetiva vem do default_* do material
MIRROR = {
    "default_material_print_temperature": ["material_print_temperature",
                                           "material_print_temperature_layer_0",
                                           "material_initial_print_temperature",
                                           "material_final_print_temperature"],
    "default_material_bed_temperature": ["material_bed_temperature",
                                         "material_bed_temperature_layer_0"],
}


def read_inst(path: Path) -> dict[str, str]:
    """Le um .inst.cfg do Cura (ini-like, com % escapado)."""
    cp = configparser.ConfigParser(interpolation=None)
    cp.read_string(path.read_text(encoding="utf-8-sig").replace("%", "%%"))
    return dict(cp["values"]) if cp.has_section("values") else {}


def find_cfg(folder: Path, *fragments: str) -> Path | None:
    """Acha o .inst.cfg cujo nome contem todos os fragmentos (o Cura usa '+' ou
    '_' antes do %23 conforme o tipo de container, entao nao se chuta o nome)."""
    for path in sorted(folder.glob("*.inst.cfg")):
        if all(frag in path.name for frag in fragments):
            return path
    return None


def read_cfg(folder: Path, *fragments: str) -> dict[str, str]:
    path = find_cfg(folder, *fragments)
    if path is None:
        raise FileNotFoundError(f"nenhum .inst.cfg com {fragments} em {folder}")
    return read_inst(path)



def read_material(path: Path) -> dict[str, str]:
    """Le as settings genericas de um .fdm_material (ignora blocos <machine>)."""
    root = ET.parse(path).getroot()
    ns = {"m": root.tag.split("}")[0].strip("{")}
    out: dict[str, str] = {}
    settings = root.find("m:settings", ns)
    for props in root.findall("m:properties", ns):
        for key, setting in (("density", "material_density"), ("diameter", "material_diameter")):
            node = props.find(f"m:{key}", ns)
            if node is not None and node.text:
                out[setting] = node.text.strip()
    for node in settings.findall("m:setting", ns):  # somente filhas diretas: as genericas
        key = MATERIAL_MAP.get(node.get("key", ""))
        if key and node.text:
            out[key] = node.text.strip()
    return out


NUM = re.compile(r"^-?\d+(\.\d+)?$")


def plain(value: str, known: dict[str, float]) -> str:
    """Resolve '=expr' simples para numero; devolve o resto como esta."""
    if not isinstance(value, str) or not value.startswith("="):
        return value
    expr = value[1:]
    try:
        result = eval(expr, {"__builtins__": {}}, dict(known))  # noqa: S307 - expressoes do Cura
    except Exception:
        return value
    return str(round(float(result), 6))


def resolve(layers: list[dict[str, str]], known: dict[str, float]) -> dict[str, str]:
    """Primeiro container que define uma chave vence (ordem = prioridade)."""
    out: dict[str, str] = {}
    for layer in layers:
        for key, value in layer.items():
            if value != "" and key not in out:
                out[key] = plain(value, known)
    return out


def derived(settings: dict[str, str]) -> dict[str, str]:
    """Recalcula os settings que o Cura deriva de outro (o CuraEngine calcula os
    defaults no carregamento da definicao e nao refaz quando o valor de origem
    chega por -s, entao infill/top_layers ficariam no default)."""
    out: dict[str, str] = {}
    geom = {"layer_height": 0.2, "top_bottom_thickness": 0.8, "infill_sparse_density": 20.0,
            "line_width": 0.4, "wall_thickness": 0.8, "speed_print": 50.0}
    for key, default in geom.items():
        if key in settings:
            try:
                geom[key] = float(settings[key])
            except ValueError:
                pass
    layers = math.ceil(round(geom["top_bottom_thickness"] / geom["layer_height"], 4))
    out["top_layers"] = out["bottom_layers"] = str(max(1, layers))
    out["top_thickness"] = out["bottom_thickness"] = str(geom["top_bottom_thickness"])
    pattern = settings.get("infill_pattern", "grid")
    mult = {"grid": 2, "triangles": 3, "trihexagon": 3, "cubic": 3, "cubicsubdiv": 3,
            "tetrahedral": 2, "quarter_cubic": 2, "lightning": 1.6}.get(pattern, 1.0)
    density = geom["infill_sparse_density"]
    out["infill_line_width"] = str(geom["line_width"])
    out["infill_line_distance"] = ("0" if density == 0 else
                                   f"{geom['line_width'] * 100 / density * mult:g}")
    if "speed_print" in settings:  # so quando o perfil mexe em speed_print
        sp = geom["speed_print"]
        out.update({"speed_infill": f"{sp:g}", "speed_wall": f"{sp / 2:g}", "speed_wall_x": f"{sp / 2:g}",
                    "speed_wall_0": f"{sp / 2:g}", "speed_topbottom": f"{sp / 2:g}",
                    "speed_support": f"{sp / 2:g}", "speed_travel": f"{sp * 2.5:g}"})
    return {k: v for k, v in out.items() if k not in settings}


def build_settings(quality_type: str, quality_name: str, drop_user: bool,
                   overrides: dict[str, str] | None = None) -> dict[str, str]:
    cc = CURA_USER / "quality_changes"
    glob: list[dict[str, str]] = [
        read_cfg(CURA_USER / "user", "Ender-3", "user"),
        read_cfg(cc, "creality_ender3pro_", quality_name),
        {},
        read_inst(RES / f"quality/creality/base/base_global_{quality_type}.inst.cfg"),
        {},
        {},
        read_cfg(CURA_USER / "definition_changes", "Ender-3", "_settings"),
    ]
    ext: list[dict[str, str]] = [
        read_cfg(CURA_USER / "user", "extruder_0", "user"),
        read_cfg(cc, "extruder_0", quality_name),
        {},
        read_inst(RES / f"quality/creality/base/base_0.4_PLA_{quality_type}.inst.cfg"),
        read_material(RES / "materials/generic_pla_175.xml.fdm_material"),
        read_inst(RES / "variants/creality/creality_ender3pro_0.4.inst.cfg"),
        read_cfg(CURA_USER / "definition_changes", "extruder_0", "_settings"),
    ]
    if drop_user:
        glob[0] = {}
        ext[0] = {}
    known = {"layer_height": 0.28, "layer_height_0": 0.28, "line_width": 0.4,
             "machine_nozzle_size": 0.4, "infill_sparse_density": 15.0}
    settings = resolve(glob + ext, known)
    # --set: vence sobre os perfis. As chaves derivadas saem fora para o
    # derived() recalcular em cima do valor pedido (senao o infill_line_distance
    # antigo fica valendo e a densidade pedida nao chega no gcode).
    for chave in ("infill_line_distance", "top_layers", "bottom_layers",
                  "top_thickness", "bottom_thickness"):
        settings.pop(chave, None)
    settings.update(overrides or {})
    # settings que só existem na cadeia de definicoes: sem isso o CuraEngine
    # pega o default do fdmprinter e erra tudo que deriva dele. A creality_base
    # define speed_print = 50 (o fdmprinter diz 60), e era por isso que a minha
    # fatia saía com a parede externa a 30 mm/s em vez dos 25 do Cura.
    if "speed_print" not in settings:
        velocidade = definition_values().get("speed_print")
        if velocidade:
            settings["speed_print"] = velocidade
    for source, targets in MIRROR.items():
        for target in targets:
            # só preenche se o alvo não veio de um container de prioridade
            # maior (quality_changes do perfil vence o default_* do material:
            # era isso que fazia o 195 do perfil novo virar 200)
            settings.setdefault(target, settings[source])
    settings.update(derived(settings))
    gaps = expand_templates(settings)
    if gaps:
        print(f"[aviso] placeholders nao resolvidos no gcode: {sorted(set(gaps))}")
    return settings


MISSING_RE = re.compile(r"no value given: ?'?(\w+)'?")

# Sem estes o CuraEngine 5.13 nao fatia pela CLI: o Cura sempre manda o valor
# resolvido e aqui a ausencia vira travamento ou crash (0xC0000409), nao erro.
REQUIRED = {
    "machine_heated_bed": "true",
    "machine_extruder_count": "1",
    "roofing_layer_count": "0",
    "flooring_layer_count": "0",
    "center_object": "true",  # sem isso a peca sai com o canto na mesa, nao centrada
}

TEMPLATE_RE = re.compile(r"\{(\w+)\}")


def definition_values() -> dict[str, str]:
    """Valores simples das 3 definicoes da maquina (fdmprinter -> creality_base ->
    creality_ender3pro, o ultimo que define ganha). Serve para resolver
    placeholders como {machine_depth} que nao estao na pilha de perfis."""
    out: dict[str, str] = {}

    def walk(node: dict) -> None:
        for key, value in node.items():
            if isinstance(value, dict):
                if "default_value" in value:
                    out[key] = str(value["default_value"])
                elif "value" in value and not isinstance(value["value"], dict) \
                        and not str(value["value"]).startswith(("=", "math.", "round")):
                    out[key] = str(value["value"])
                walk(value)

    for name in ("fdmprinter.def.json", "creality_base.def.json", "creality_ender3pro.def.json"):
        walk(json.loads((RES / "definitions" / name).read_text(encoding="utf-8")))
    return out


def expand_templates(settings: dict[str, str], rounds: int = 3) -> list[str]:
    """Troca {setting} dentro de machine_start/end_gcode pelo valor resolvido.

    O Cura faz isso na GUI; passando o gcode por -s o CuraEngine escreve as
    chaves literais, o que a impressora nao entende."""
    fallback = definition_values()
    for _ in range(rounds):
        changed = False
        for key, value in list(settings.items()):
            if "{" not in value:
                continue
            def sub(m: re.Match) -> str:
                return settings.get(m.group(1)) or fallback.get(m.group(1), m.group(0))
            new = TEMPLATE_RE.sub(sub, value)
            if new != value:
                settings[key] = new
                changed = True
        if not changed:
            break
    gaps: list[str] = []
    for value in settings.values():
        gaps += [m.group(1) for m in TEMPLATE_RE.finditer(value)]
    return gaps

_DEFS_CACHE: dict[str, object] = {}


def definition_defaults() -> dict[str, object]:
    """Mapa setting -> default_value, lido do fdmprinter.def.json."""
    if not _DEFS_CACHE:
        data = json.loads((RES / "definitions/fdmprinter.def.json").read_text(encoding="utf-8"))
        found: dict[str, object] = {}

        def walk(node: dict) -> None:
            for key, value in node.items():
                if isinstance(value, dict):
                    if "default_value" in value or "value" in value:
                        found.setdefault(key, value.get("default_value", 0))
                    walk(value)

        walk(data.get("settings", data))
        _DEFS_CACHE.update(found)
    return _DEFS_CACHE


def run_engine(stl: Path, gcode: Path, settings: dict[str, str]) -> int:
    """Roda o CuraEngine. Alguns settings nao tem default na cadeia de definicoes
    (o Cura sempre envia o valor resolvido), entao a ausencia e corrigida pelo
    default do fdmprinter e o slice e repetido.

    Todo caminho vai com '/' (as_posix): com '\\\\' o CommandLineToArgvW do Windows
    come a barra antes da aspa e o CuraEngine perde o arquivo (fica varrendo o disco).
    """
    extra: dict[str, str] = dict(REQUIRED)
    for attempt in range(12):
        args = [CURA_ENGINE.as_posix(), "slice",
                "-d", f"{(RES / 'definitions').as_posix()};{(RES / 'extruders').as_posix()}",
                "-j", (RES / "definitions/fdmprinter.def.json").as_posix(),
                "-j", (RES / "definitions/creality_base.def.json").as_posix(),
                "-j", (RES / "definitions/creality_ender3pro.def.json").as_posix()]
        merged = {**settings, **extra}
        args += sum([["-s", f"{k}={v}"] for k, v in sorted(merged.items())], [])
        # settings por extrusora (infill, paredes, velocidades) so valem se
        # repetidos no escopo da extrusora; sem isso o CuraEngine usa o default.
        args += ["-e0"] + sum([["-s", f"{k}={v}"] for k, v in sorted(merged.items())], [])
        args += ["-l", stl.as_posix(), "-o", gcode.as_posix()]
        proc = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=180)
        if proc.returncode == 0 and gcode.exists() and gcode.stat().st_size > 1024:
            return 0
        errors = [ln for ln in proc.stderr.splitlines() if "[error]" in ln]
        missing = next((m.group(1) for ln in errors if (m := MISSING_RE.search(ln))), None)
        if missing and missing not in merged:
            fallback = definition_defaults().get(missing, 0)
            extra[missing] = str(fallback)
            print(f"[engine] setting sem valor na cadeia: {missing} -> {fallback} (retry)")
            continue
        for line in errors[:4] or proc.stderr.splitlines()[-4:]:
            print("   ", line[:170])
        return proc.returncode
    print("[engine] desisti apos 12 tentativas")
    return 1



def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl", required=True)
    ap.add_argument("--profile", default="low", choices=["low", "standard"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-user", action="store_true",
                    help="ignora o container de user changes (usa o perfil puro)")
    ap.add_argument("--dump", action="store_true", help="mostra os settings resolvidos")
    ap.add_argument("--set", action="append", default=[], metavar="CHAVE=VALOR",
                    help="sobrescreve setting do perfil (ex.: infill_sparse_density=30)")
    ap.add_argument("--quality", default=None,
                    help="nome do quality_changes a usar (ex.: low_quality_2026_v1_%%232)")
    args = ap.parse_args()

    overrides: dict[str, str] = {}
    for item in args.set:
        if "=" not in item:
            print(f"[erro] --set espera CHAVE=VALOR, veio {item!r}")
            return 2
        chave, valor = item.split("=", 1)
        overrides[chave.strip()] = valor.strip()

    quality_name = args.quality or f"{args.profile}_quality_2026_v1"
    settings = build_settings(args.profile, quality_name, args.no_user, overrides)
    if args.dump:
        for key in sorted(settings):
            print(f"  {key} = {settings[key]!r}")
    stl = Path(args.stl).resolve()
    gcode = Path(args.out).resolve()
    code = run_engine(stl, gcode, settings)
    if code == 0 and gcode.exists():
        size = gcode.stat().st_size
        print(f"[ok] {gcode} ({size/1024:.0f} KB)")
    else:
        print(f"[falhou] exit={code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
