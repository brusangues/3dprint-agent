"""Cotas (dimension lines) em matplotlib, estilo desenho técnico.

Uma cota é: linha de extensão em cada ponta, linha de medida paralela ao
trecho com seta nas duas pontas, e o valor no meio. A função `cota()` recebe
os dois pontos do trecho medido (em coordenadas de dados) e desenha tudo.
"""

from __future__ import annotations

COR_COTA = "#1f4e9c"
COR_EXT = "#7a8ba6"


def cota(ax, p1, p2, texto, offset=8.0, cor=COR_COTA, fonte=9.5, fonte_borda="white"):
    """Desenha a cota do trecho p1->p2 deslocada `offset` na perpendicular.

    Negativo desloca para baixo/esquerda, positivo para cima/direita.
    """
    (x1, y1), (x2, y2) = p1, p2
    horizontal = abs(x2 - x1) >= abs(y2 - y1)
    if horizontal:
        dy = offset
        ax.annotate("", xy=(x1, y1 + dy), xytext=(x2, y2 + dy),
                    arrowprops=dict(arrowstyle="<|-|>", lw=0.9, color=cor, shrinkA=0, shrinkB=0))
        for x, y in ((x1, y1), (x2, y2)):
            ax.plot([x, x], [y, y + dy * 1.18], lw=0.7, color=COR_EXT, zorder=1)
        ax.text((x1 + x2) / 2, y1 + dy + (2.0 if dy > 0 else -2.0), texto,
                ha="center", va="bottom" if dy > 0 else "top", fontsize=fonte, color=cor,
                bbox=dict(fc=fonte_borda, ec="none", pad=1.2), zorder=5)
    else:
        dx = offset
        ax.annotate("", xy=(x1 + dx, y1), xytext=(x2 + dx, y2),
                    arrowprops=dict(arrowstyle="<|-|>", lw=0.9, color=cor, shrinkA=0, shrinkB=0))
        for x, y in ((x1, y1), (x2, y2)):
            ax.plot([x, x + dx * 1.18], [y, y], lw=0.7, color=COR_EXT, zorder=1)
        ax.text(x1 + dx + (2.0 if dx > 0 else -2.0), (y1 + y2) / 2, texto,
                ha="left" if dx > 0 else "right", va="center", fontsize=fonte, color=cor,
                rotation=90, bbox=dict(fc=fonte_borda, ec="none", pad=1.2), zorder=5)


def cota_horizontal_encadeada(ax, xs, y, offset, rotulos=None, **kw):
    """Cota encadeada: mede cada trecho entre xs consecutivos."""
    for i in range(len(xs) - 1):
        texto = rotulos[i] if rotulos else f"{xs[i + 1] - xs[i]:g}"
        cota(ax, (xs[i], y), (xs[i + 1], y), texto, offset=offset, **kw)


def cota_vertical_encadeada(ax, ys, x, offset, rotulos=None, **kw):
    for i in range(len(ys) - 1):
        texto = rotulos[i] if rotulos else f"{ys[i + 1] - ys[i]:g}"
        cota(ax, (x, ys[i]), (x, ys[i + 1]), texto, offset=offset, **kw)
