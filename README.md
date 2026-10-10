# 3dprint-agent

Framework de modelagem paramétrica para impressão 3D em Python.
Gera peças a partir de código e exporta `.stl` (binário/ASCII) e `.obj`.

**Unidade: milímetros.** O STL não guarda unidade, então todo o código
assume mm — 2 cm = 20 mm. É a convenção do Cura, PrusaSlicer e Bambu
Studio.

## Ambiente

Python **3.12** num conda env isolado.

```bash
conda env create -f environment.yml    # cria o env
conda activate print3d

conda run -n print3d python examples/make_cube.py
conda run -n print3d python -m pytest tests/ -q
```

## Uso rápido

```python
from print3d import csg, primitives as prim
from print3d.stl import write_stl
from print3d.validate import validate_mesh

peca = csg.subtract(
    prim.box(16, 10, 40).to_origin_corner(),
    prim.box(4, 4, 10).to_origin_corner().translate(6, 3, 30),
)
report = validate_mesh(peca)
if report.ok:
    write_stl(peca, "out/bloco.stl")
else:
    print(report.summary())   # não exporta malha quebrada
```

## Primitivas

| função | o que faz |
|---|---|
| `box(w, d, h)` / `cube(a)` | caixa retangular e cubo |
| `cylinder(r, h, segments)` | cilindro com tampa |
| `frustum(r_bot, r_top, h)` | cone ou tronco de cone |
| `sphere(r, segments, rings)` | esfera UV |
| `washer(r_ext, r_int, h)` | anel / arruela |
| `lathe(perfil, segments)` | sólido de revolução a partir de um perfil (r, z) |
| `box_with_pocket(w, d, h, pw, pd, ph)` | caixa com cavidade reta no topo |

## Booleanas (CSG)

Backend: **manifold3d**, um kernel de geometria robusta. Faz união,
subtração e interseção com topologia exata.

```python
csg.union(a, b)        # a + b
csg.subtract(a, b)     # a - b
csg.difference(a, b)   # alias do subtract
csg.intersect(a, b)    # a ∩ b
csg.csg_available()    # False se o kernel não estiver instalado
```

Sem o kernel, o framework continua funcionando: as primitivas de
`compound.py` constroem as peças sem booleana, e os testes de CSG são
pulados automaticamente em vez de quebrar a suíte.

### Por que BSP não serve (medido, não é opinião)

O algoritmo BSP do csg.js — o algoritmo de referência em JavaScript —
**perde geometria** em subtração com faces coplanares. Medido neste
repositório, rodando o csg.js original em Node:

- caixa 20×20×20 menos furo 5×15×15: volume correto (7062,5 mm³), mas a
  área do topo dá 318,75 mm² quando deveria dar 337,5
- número de Euler dá −3 em vez de 2, ou seja, a casca não fecha
- o mesmo erro aparece na implementação em Python e no JS original

O sintoma é silencioso: o volume acerta e o arquivo abre no slicer, mas a
peça sai com buraco. O manifold3d acerta volume, área e Euler.

## O que a validação checa

O STL não guarda índice de vértice compartilhado, então o slicer
reconstrói as arestas por coalescência de posição. Se sobrar qualquer
aresta com uma única face, o fatiador ou descarta a peça ou abre um buraco
no meio do caminho de extrusão. `validate_mesh()` reprova, com mensagem
explícita, cada um desses casos:

- **aresta de contorno** — a peça não é fechada (não imprime)
- **aresta não-manifold** — mais de 2 faces na mesma aresta
- **face degenerada** — vértices coincidentes ou colineares (área zero)
- **winding inconsistente** — algumas normais apontam para dentro
- **volume negativo** — normais invertidas
- **aviso de aresta mínima** — abaixo de 0.05 mm, fora do alcance de um
  bico de 0.4 mm

O bom teste de peça nova é comparar o volume medido com o teórico: se
bate e a validação passa, a geometria está certa. A suíte tem testes que
conferem a área de cada plano individualmente, porque o volume sozinho
não pega geometria perdida.

## Convenções

- faces em sentido **anti-horário visto de fora**, para a normal apontar
  para o exterior
- primitivas nascem **centradas na origem** (convenção Blender/Cura);
  use `to_origin_corner()` ou `move_to(0, 0, 0)` para sentar a peça na mesa
- `box_with_pocket` nasce com o canto em (0,0,0), sentada na mesa
- `mirror()` inverte a ordem das faces junto com os vértices — espelhar
  só as coordenadas deixa a normal para dentro e o volume negativo
- `rotate()` preserva volume (fórmula de Rodrigues completa)

## Estrutura

```
print3d/
  mesh.py        Mesh: vértices, faces, medidas (volume, área, bbox),
                 transformações (translate, scale, rotate, mirror)
  primitives.py  caixa, cilindro, cone, esfera, anel, revolução
  compound.py    caixa com cavidade reta (casca fechada direta, sem CSG)
  csg.py         união / subtração / interseção via manifold3d
  validate.py    malha fechada, winding, degeneradas, fusão de vértices
  stl.py         escrita/leitura de STL binário e ASCII, e OBJ
  preview.py     render PNG com z-buffer próprio
examples/
  make_cube.py                cubo 20×20×20
  make_block_with_pocket.py   bloco 16×10×40 com cavidade 4×4×10
  make_plate_with_hole.py     placa 60×40×6 com 3 furos circulares
tests/test_print3d.py   26 testes
out/                    arquivos gerados
```

## Notas de implementação

**Preview.** Rasterizador próprio com z-buffer por pixel, em vez de
mplot3d. O mplot3d ordena faces por distância média ao centro e
produz raios-X: um furo passante aparece atravessado pelo fundo. Com
z-buffer, uma peça furada aparece furada.

**Erros já corrigidos que valem lembrar** — todos achados por teste, não
por leitura:

- `rotate()` sem o termo `u·v` da fórmula de Rodrigues encolhia a peça
- winding invertido nos quads do meio da esfera
- `frustum` com raio 0 gerava 64 faces degeneradas no pólo
- o preview misturava unidades (área em tela, pesos em pixel) e o
  triângulo inteiro sumia
- ordem de multiplicação das matrizes de câmera deitava a peça