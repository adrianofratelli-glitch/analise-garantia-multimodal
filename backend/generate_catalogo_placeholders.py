"""Gera placeholders para as fotos de referência do catálogo (4 por SKU).

ATENCAO: placeholders NAO tem valor de demo real — sao formas e texto, nao
fotos reais do produto. Servem so para testar o pipeline (embed + $vectorSearch
de identidade) antes das fotos reais chegarem.

Uso (a partir de backend/):
    python generate_catalogo_placeholders.py
Gera os arquivos em ../seed_images/catalogo/<sku>/1.jpg .. 4.jpg.

Para usar fotos reais, so substituir os arquivos nesse mesmo caminho/nome
(mesma pasta por sku, 4 arquivos numerados) e rodar seed_catalogo_fotos.py de novo.
"""

import os

from PIL import Image, ImageDraw, ImageFont

from catalogo_produtos_data import CATALOGO_PRODUTOS

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "seed_images", "catalogo")
W, H = 800, 600

COR_CATEGORIA = {
    "cadeira":      (38, 70, 83),
    "colchao":      (42, 157, 143),
    "guarda_roupa": (138, 84, 40),
}

# Pequena variação de tom por índice de foto — simula ângulos/fotos diferentes
# do mesmo produto sem depender de imagens reais.
VARIACAO = [0, 18, -18, 32]


def _font(size):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _shade(rgb, delta):
    return tuple(max(0, min(255, c + delta)) for c in rgb)


def gerar():
    os.makedirs(OUT_DIR, exist_ok=True)
    f_tit, f_sub = _font(34), _font(24)
    total = 0

    for p in CATALOGO_PRODUTOS:
        pasta = os.path.join(OUT_DIR, p["sku"])
        os.makedirs(pasta, exist_ok=True)
        cor_base = COR_CATEGORIA.get(p["categoria"], (60, 60, 60))

        for i in range(1, p["n_fotos"] + 1):
            cor = _shade(cor_base, VARIACAO[(i - 1) % len(VARIACAO)])
            img = Image.new("RGB", (W, H), cor)
            d = ImageDraw.Draw(img)
            d.text((40, 30), p["sku"], font=f_tit, fill=(255, 255, 255))
            d.text((40, 80), f"{p['nome']} — foto {i}/{p['n_fotos']}", font=f_sub, fill=(230, 230, 230))
            d.rectangle([560, 180, 740, 460], outline=(255, 255, 255), width=6)
            d.text((40, H - 50), "PLACEHOLDER — substituir por foto real do catalogo",
                    font=f_sub, fill=(255, 210, 180))

            caminho = os.path.join(pasta, f"{i}.jpg")
            img.save(caminho, "JPEG", quality=85)
            print("ok", os.path.relpath(caminho, OUT_DIR))
            total += 1

    print(f"\n{total} placeholders em {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    gerar()
