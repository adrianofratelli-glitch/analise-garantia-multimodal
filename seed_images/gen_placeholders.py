"""Gera as 15 imagens placeholder de seed_images/ (cad_01..05, col_01..05, gr_01..05).

São apenas placeholders para o seed rodar de ponta a ponta sem fotos reais —
cada PNG mostra o SKU e o defeito do chamado correspondente. Para uma demo de
verdade, substitua por fotos reais dos produtos com os mesmos nomes de arquivo.

    python seed_images/gen_placeholders.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

# importa os metadados dos chamados para casar arquivo -> rótulo
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from seed_data import CHAMADOS_SEED  # noqa: E402

AQUI = Path(__file__).resolve().parent

CORES = {
    "cadeira": (0, 104, 74),       # verde MongoDB
    "colchao": (0, 70, 110),       # azul
    "guarda_roupa": (120, 60, 20), # madeira
}

from defeitos_catalog import categoria_do_sku  # noqa: E402


def gerar():
    for item in CHAMADOS_SEED:
        categoria = categoria_do_sku(item["sku"])
        cor = CORES.get(categoria, (40, 40, 40))
        img = Image.new("RGB", (800, 600), cor)
        d = ImageDraw.Draw(img)

        defeito = item["checklist"][0] if item["checklist"] else "—"
        linhas = [
            item["numero_chamado"],
            item["sku"],
            f"categoria: {categoria}",
            f"defeito: {defeito}",
            "",
            "(placeholder — troque por foto real)",
        ]
        y = 60
        for ln in linhas:
            d.text((50, y), ln, fill=(255, 255, 255))
            y += 40

        # moldura para parecer uma "foto"
        d.rectangle([20, 20, 780, 580], outline=(255, 255, 255), width=3)

        destino = AQUI / item["arquivo"]
        img.save(destino, "PNG")
        print(f"  ✓ {destino.name}")

    print(f"\n{len(CHAMADOS_SEED)} placeholders gerados em {AQUI}")


if __name__ == "__main__":
    gerar()
