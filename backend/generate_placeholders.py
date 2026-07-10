"""Gera placeholders de seed para validar o pipeline end-to-end.

ATENCAO: placeholders NAO tem valor de demo de cliente — sao formas e texto,
nao defeitos reais. Servem so para testar S3 + embed multimodal + $vectorSearch
+ Claude enquanto as fotos de catalogo da loja nao chegam. Substitua
por imagens reais (mesmos nomes de arquivo) antes de qualquer apresentacao.

Uso (a partir de backend/):
    python generate_placeholders.py
Gera os arquivos em ../seed_images/ com os nomes referenciados em seed_data.py.
"""

import os

from PIL import Image, ImageDraw, ImageFont

try:
    from seed_data import CHAMADOS_SEED
except ImportError as e:
    raise SystemExit("Rode a partir de backend/ (precisa importar seed_data.py).") from e

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "seed_images")
W, H = 800, 600

# Cor de fundo por categoria — dá alguma separação visual entre famílias de produto.
COR_CATEGORIA = {
    "cadeira":      (38, 70, 83),    # azul-petróleo
    "colchao":      (42, 157, 143),  # verde
    "guarda_roupa": (138, 84, 40),   # marrom
}

# Cor da "marca de defeito" por tipo, derivada do checklist.
COR_DEFEITO = {
    "estrutural": (231, 111, 81),   # laranja
    "funcional":  (244, 162, 97),   # âmbar
    "estetico":   (233, 196, 106),  # amarelo
    "faltante":   (200, 200, 200),  # cinza
}

# Mapa item -> tipo (espelha defeitos_catalog para o script ser standalone).
ITEM_TIPO = {
    "perna_quebrada": "estrutural", "rodinha_solta": "estrutural", "base_travada": "funcional",
    "pistao_vazando": "funcional", "estofado_rasgado": "estetico", "mancha": "estetico",
    "parafuso_faltando": "faltante", "afundamento": "estrutural", "molas_salientes": "estrutural",
    "rasgo_tecido": "estetico", "costura_solta": "estetico", "odor_forte": "funcional",
    "porta_desalinhada": "funcional", "dobradica_quebrada": "estrutural",
    "painel_lascado": "estrutural", "arranhado": "estetico", "puxador_faltando": "faltante",
}


def _font(size):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    palavras, linhas, atual = text.split(), [], ""
    for p in palavras:
        teste = (atual + " " + p).strip()
        if draw.textlength(teste, font=font) <= max_w:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def _marca_defeito(draw, tipo, box):
    """Desenha uma forma simples representando o tipo de defeito — varia o sinal visual."""
    x0, y0, x1, y1 = box
    cor = COR_DEFEITO.get(tipo, (255, 255, 255))
    if tipo == "estrutural":  # rachadura em zigue-zague
        pts = [(x0, y0), (x0 + 60, y0 + 40), (x0 + 20, y0 + 80),
               (x0 + 80, y0 + 130), (x0 + 30, y0 + 180)]
        draw.line(pts, fill=cor, width=8, joint="curve")
    elif tipo == "estetico":  # mancha / círculo
        draw.ellipse([x0, y0, x0 + 150, y0 + 150], outline=cor, width=10)
        draw.ellipse([x0 + 40, y0 + 40, x0 + 110, y0 + 110], fill=cor)
    elif tipo == "funcional":  # seta para baixo (afunda / não segura)
        draw.line([(x0 + 75, y0), (x0 + 75, y0 + 150)], fill=cor, width=10)
        draw.polygon([(x0 + 45, y0 + 120), (x0 + 105, y0 + 120), (x0 + 75, y0 + 180)], fill=cor)
    else:  # faltante — X / lacuna
        draw.line([(x0, y0), (x0 + 150, y0 + 150)], fill=cor, width=10)
        draw.line([(x0 + 150, y0), (x0, y0 + 150)], fill=cor, width=10)


def gerar():
    os.makedirs(OUT_DIR, exist_ok=True)
    f_tit, f_sub, f_txt = _font(34), _font(24), _font(20)

    for c in CHAMADOS_SEED:
        cat = c["categoria"]
        img = Image.new("RGB", (W, H), COR_CATEGORIA.get(cat, (50, 50, 50)))
        d = ImageDraw.Draw(img)

        d.text((40, 30), c["numero_chamado"], font=f_tit, fill=(255, 255, 255))
        d.text((40, 80), f"{cat.upper()} · {c['produto']['nome']}", font=f_sub, fill=(230, 230, 230))

        item = c["checklist"][0] if c["checklist"] else ""
        tipo = ITEM_TIPO.get(item, "estetico")
        d.text((40, 130), f"defeito: {item}  ({tipo})", font=f_txt, fill=(255, 230, 200))

        _marca_defeito(d, tipo, (560, 180, 740, 360))

        y = 200
        for linha in _wrap(d, c["descricao_cliente"], f_txt, 480):
            d.text((40, y), linha, font=f_txt, fill=(245, 245, 245))
            y += 30

        d.text((40, H - 50), "PLACEHOLDER — substituir por foto real",
               font=f_txt, fill=(255, 180, 180))

        caminho = os.path.join(OUT_DIR, c["imagem_arquivo"])
        img.save(caminho, "JPEG", quality=85)
        print("ok", c["imagem_arquivo"])

    print(f"\n{len(CHAMADOS_SEED)} placeholders em {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    gerar()
