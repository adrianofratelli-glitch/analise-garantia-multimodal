"""Fotos de referência do catálogo (FONTE DE SEED) — usadas na verificação de
identidade: "a foto que o cliente subiu é realmente do produto que ele comprou?"

Cada SKU tem 4 fotos de referência (ângulos/detalhes diferentes do produto
sem defeito). seed_catalogo_fotos.py embeda cada uma (input_type="document")
e grava em `catalogo_fotos`. Em runtime, a foto do cliente é comparada via
$vectorSearch contra as 4 fotos do SKU do pedido — score baixo = produto
provavelmente errado/divergente, não necessariamente "sem defeito".

Arquivos esperados em seed_images/catalogo/<sku>/1.jpg .. 4.jpg.
"""

CATALOGO_PRODUTOS = [
    {"sku": "CAD-OFF-PRO", "nome": "Cadeira Office Pro", "categoria": "cadeira", "n_fotos": 4},
    {"sku": "CAD-GAMER-X", "nome": "Cadeira Gamer X", "categoria": "cadeira", "n_fotos": 4},
    {"sku": "COL-MOLAS-Q", "nome": "Colchao Molas Ensacadas Queen", "categoria": "colchao", "n_fotos": 4},
    {"sku": "GR-6PORTAS", "nome": "Guarda-Roupa 6 Portas", "categoria": "guarda_roupa", "n_fotos": 4},
]
