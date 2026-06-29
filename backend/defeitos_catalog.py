"""
Catálogo de defeitos da PoV "MM Análise de Garantia" (MadeiraMadeira).

Fonte única da verdade para:
  - PRODUTOS / SKUs e suas categorias
  - CATALOGO_DEFEITOS (itens de checklist por categoria)
  - compor_frase(...)        -> frase de análise (idêntica no seed e no runtime)
  - derivar_tipo_defeito(...) -> classificação grosseira do defeito

IMPORTANTE: tanto seed.py quanto main.py importam compor_frase e
derivar_tipo_defeito DESTE módulo. Assim a frase usada para gerar o embedding
no seed é byte-a-byte igual à frase usada em runtime, garantindo que o
$vectorSearch compare vetores construídos do mesmo jeito.
"""

# --------------------------------------------------------------------------- #
# Produtos / SKUs do catálogo da PoV
# --------------------------------------------------------------------------- #
PRODUTOS = {
    "CAD-OFF-PRO":  {"nome": "Cadeira de Escritório Pro",   "categoria": "cadeira"},
    "CAD-GAMER-X":  {"nome": "Cadeira Gamer X",             "categoria": "cadeira"},
    "COL-MOLAS-Q":  {"nome": "Colchão de Molas Queen",      "categoria": "colchao"},
    "COL-ESPUMA-S": {"nome": "Colchão de Espuma Solteiro",  "categoria": "colchao"},
    "GR-6PORTAS":   {"nome": "Guarda-Roupa 6 Portas",       "categoria": "guarda_roupa"},
    "GR-3PORTAS":   {"nome": "Guarda-Roupa 3 Portas",       "categoria": "guarda_roupa"},
}

CATEGORIA_LABEL = {
    "cadeira": "Cadeira",
    "colchao": "Colchão",
    "guarda_roupa": "Guarda-Roupa",
}

# --------------------------------------------------------------------------- #
# Checklist de defeitos por categoria
# Cada item: id (estável), label (exibido no front), tipo (agrupamento)
# --------------------------------------------------------------------------- #
CATALOGO_DEFEITOS = {
    "cadeira": [
        {"id": "cad_pistao",   "label": "Pistão a gás não sustenta a altura",      "tipo": "mecanismo"},
        {"id": "cad_rodizio",  "label": "Rodízio quebrado, solto ou travando",     "tipo": "estrutural"},
        {"id": "cad_estofado", "label": "Estofado rasgado ou descosturado",        "tipo": "estofamento"},
        {"id": "cad_base",     "label": "Base/aranha trincada ou empenada",        "tipo": "estrutural"},
        {"id": "cad_encosto",  "label": "Encosto solto ou com folga excessiva",    "tipo": "estrutural"},
        {"id": "cad_braco",    "label": "Apoio de braço quebrado",                 "tipo": "estrutural"},
    ],
    "colchao": [
        {"id": "col_afundamento", "label": "Afundamento / marca permanente",       "tipo": "conforto"},
        {"id": "col_mola",        "label": "Mola estourada ou aparente",           "tipo": "estrutural"},
        {"id": "col_costura",     "label": "Costura aberta ou etiqueta solta",     "tipo": "acabamento"},
        {"id": "col_espuma",      "label": "Espuma esfarelando",                   "tipo": "material"},
        {"id": "col_mancha",      "label": "Mancha de fábrica no tecido",          "tipo": "acabamento"},
    ],
    "guarda_roupa": [
        {"id": "gr_porta",     "label": "Porta desalinhada ou que não fecha",      "tipo": "montagem"},
        {"id": "gr_dobradica", "label": "Dobradiça quebrada",                      "tipo": "ferragem"},
        {"id": "gr_corredica", "label": "Corrediça de gaveta travando",           "tipo": "ferragem"},
        {"id": "gr_mdf",       "label": "MDF inchado ou lascado",                  "tipo": "material"},
        {"id": "gr_espelho",   "label": "Espelho trincado",                        "tipo": "acabamento"},
        {"id": "gr_montagem",  "label": "Furação de montagem incorreta",          "tipo": "montagem"},
    ],
}

# Índice rápido: (categoria, id) -> item
_ITENS_POR_ID = {
    (categoria, item["id"]): item
    for categoria, itens in CATALOGO_DEFEITOS.items()
    for item in itens
}


# --------------------------------------------------------------------------- #
# Helpers de produto
# --------------------------------------------------------------------------- #
def categoria_do_sku(sku: str) -> str:
    """Retorna a categoria ('cadeira'|'colchao'|'guarda_roupa') de um SKU."""
    return PRODUTOS.get(sku, {}).get("categoria", "desconhecida")


def nome_do_produto(sku: str) -> str:
    """Retorna o nome comercial do produto a partir do SKU."""
    return PRODUTOS.get(sku, {}).get("nome", sku)


def _labels(categoria: str, checklist_ids):
    """Converte ids de checklist em labels legíveis, preservando a ordem do catálogo."""
    ids = set(checklist_ids or [])
    return [
        item["label"]
        for item in CATALOGO_DEFEITOS.get(categoria, [])
        if item["id"] in ids
    ]


# --------------------------------------------------------------------------- #
# Frase de análise (USADA NO SEED E NO RUNTIME — precisa ser idêntica)
# --------------------------------------------------------------------------- #
def compor_frase(sku: str, checklist_ids, descricao: str) -> str:
    """
    Monta a frase textual que descreve o chamado de garantia.

    Esta frase é o componente TEXTO do embedding multimodal (texto + imagem).
    Como seed.py e main.py chamam exatamente esta função, a frase do seed é
    idêntica à do runtime para o mesmo conjunto de entradas.
    """
    nome = nome_do_produto(sku)
    categoria = categoria_do_sku(sku)
    categoria_label = CATEGORIA_LABEL.get(categoria, categoria)

    partes = [
        f"Análise de garantia para {nome} (SKU {sku}), categoria {categoria_label}."
    ]

    itens = _labels(categoria, checklist_ids)
    if itens:
        partes.append("Defeitos apontados no checklist: " + "; ".join(itens) + ".")
    else:
        partes.append("Nenhum item de checklist marcado.")

    desc = (descricao or "").strip()
    if desc:
        partes.append(f"Relato do cliente: {desc}")

    return " ".join(partes)


# --------------------------------------------------------------------------- #
# Tipo de defeito (agrupamento grosseiro para metadados/filtros)
# --------------------------------------------------------------------------- #
def derivar_tipo_defeito(sku: str, checklist_ids) -> str:
    """
    Deriva o 'tipo_defeito' a partir do primeiro item de checklist marcado,
    respeitando a ordem do catálogo. Retorna 'indefinido' se nada for marcado.
    """
    categoria = categoria_do_sku(sku)
    ids = set(checklist_ids or [])
    for item in CATALOGO_DEFEITOS.get(categoria, []):
        if item["id"] in ids:
            return item["tipo"]
    return "indefinido"
