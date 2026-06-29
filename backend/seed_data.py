"""
Dados de seed da PoV "Análise de Garantia Multimodal" (dataset de exemplo).

  - CHAMADOS_SEED : 15 chamados de garantia já resolvidos (5 por categoria),
    cada um casado com uma imagem em seed_images/.
  - PEDIDOS_MOCK  : 3-4 pedidos fictícios usados pelo endpoint /lookup para
    descobrir quais produtos (SKUs) o cliente comprou.

Os SKUs e categorias vêm de defeitos_catalog.PRODUTOS — esta é a fonte única
da verdade. Os ids de checklist abaixo precisam existir em
defeitos_catalog.CATALOGO_DEFEITOS (senão a frase fica sem o item).

O seed (backend/seed.py) percorre CHAMADOS_SEED, compõe a frase com
compor_frase(), sobe a imagem pro S3, gera o embedding multimodal
(texto + imagem) com a Voyage e grava em POC.chamados com status="resolvido".
"""

# --------------------------------------------------------------------------- #
# Pedidos fictícios (entrada do fluxo: cliente informa o número do pedido)
# --------------------------------------------------------------------------- #
PEDIDOS_MOCK = [
    {
        "numero_pedido": "PED-100234",
        "cliente": "Joana Ribeiro",
        "data": "2026-05-12",
        "itens": ["CAD-OFF-PRO", "GR-3PORTAS"],
    },
    {
        "numero_pedido": "PED-100871",
        "cliente": "Marcos Tavares",
        "data": "2026-05-28",
        "itens": ["COL-MOLAS-Q", "COL-ESPUMA-S"],
    },
    {
        "numero_pedido": "PED-101502",
        "cliente": "Lúcia Andrade",
        "data": "2026-06-03",
        "itens": ["CAD-GAMER-X"],
    },
    {
        "numero_pedido": "PED-101990",
        "cliente": "Rafael Pimentel",
        "data": "2026-06-19",
        "itens": ["GR-6PORTAS", "CAD-OFF-PRO"],
    },
]


# --------------------------------------------------------------------------- #
# Chamados de garantia já resolvidos (base de precedentes do $vectorSearch)
# Campos por item:
#   numero_chamado   : id estável do chamado
#   sku              : SKU do produto (define a categoria)
#   checklist        : ids de defeitos marcados (de CATALOGO_DEFEITOS)
#   descricao        : relato do cliente
#   arquivo          : nome do arquivo em seed_images/
#   resolucao_final  : decisão registrada pelo analista
#   veredito         : classificação humana do precedente
# --------------------------------------------------------------------------- #
CHAMADOS_SEED = [
    # ---------------- Cadeiras ----------------
    {
        "numero_chamado": "CH-CAD-0001",
        "sku": "CAD-OFF-PRO",
        "checklist": ["cad_pistao"],
        "descricao": "A cadeira abaixa sozinha alguns minutos depois de eu sentar.",
        "arquivo": "cad_01.png",
        "resolucao_final": "Pistão a gás com defeito de fábrica. Enviada peça em garantia para troca.",
        "veredito": "procedente",
    },
    {
        "numero_chamado": "CH-CAD-0002",
        "sku": "CAD-OFF-PRO",
        "checklist": ["cad_rodizio"],
        "descricao": "Um dos rodízios quebrou e a cadeira ficou torta.",
        "arquivo": "cad_02.png",
        "resolucao_final": "Rodízio trincado na base. Kit de rodízios enviado em garantia.",
        "veredito": "procedente",
    },
    {
        "numero_chamado": "CH-CAD-0003",
        "sku": "CAD-GAMER-X",
        "checklist": ["cad_estofado"],
        "descricao": "O estofado do assento rasgou na costura depois de duas semanas.",
        "arquivo": "cad_03.png",
        "resolucao_final": "Descosturado por defeito de acabamento. Aprovada troca do assento.",
        "veredito": "procedente",
    },
    {
        "numero_chamado": "CH-CAD-0004",
        "sku": "CAD-GAMER-X",
        "checklist": ["cad_braco"],
        "descricao": "O apoio de braço quebrou quando apoiei o cotovelo.",
        "arquivo": "cad_04.png",
        "resolucao_final": "Indício de mau uso (excesso de carga). Recusada a garantia, oferecida peça com desconto.",
        "veredito": "improcedente",
    },
    {
        "numero_chamado": "CH-CAD-0005",
        "sku": "CAD-OFF-PRO",
        "checklist": ["cad_base"],
        "descricao": "A base de cinco pontas (aranha) está empenada e a cadeira balança.",
        "arquivo": "cad_05.png",
        "resolucao_final": "Base empenada de fábrica. Aprovada troca da aranha em garantia.",
        "veredito": "procedente",
    },
    # ---------------- Colchões ----------------
    {
        "numero_chamado": "CH-COL-0001",
        "sku": "COL-MOLAS-Q",
        "checklist": ["col_afundamento"],
        "descricao": "Tem um afundamento permanente no lado onde eu durmo.",
        "arquivo": "col_01.png",
        "resolucao_final": "Afundamento acima do tolerável para o tempo de uso. Aprovada troca.",
        "veredito": "procedente",
    },
    {
        "numero_chamado": "CH-COL-0002",
        "sku": "COL-MOLAS-Q",
        "checklist": ["col_mola"],
        "descricao": "Uma mola estourou e está furando o tecido por dentro.",
        "arquivo": "col_02.png",
        "resolucao_final": "Mola rompida (defeito estrutural). Aprovada troca do colchão.",
        "veredito": "procedente",
    },
    {
        "numero_chamado": "CH-COL-0003",
        "sku": "COL-ESPUMA-S",
        "checklist": ["col_espuma"],
        "descricao": "A espuma está esfarelando e soltando pó amarelo.",
        "arquivo": "col_03.png",
        "resolucao_final": "Espuma fora de especificação. Aprovada troca em garantia.",
        "veredito": "procedente",
    },
    {
        "numero_chamado": "CH-COL-0004",
        "sku": "COL-ESPUMA-S",
        "checklist": ["col_mancha"],
        "descricao": "Veio com uma mancha amarelada no tecido, parece de fábrica.",
        "arquivo": "col_04.png",
        "resolucao_final": "Mancha compatível com manuseio/armazenagem do cliente. Garantia recusada.",
        "veredito": "improcedente",
    },
    {
        "numero_chamado": "CH-COL-0005",
        "sku": "COL-MOLAS-Q",
        "checklist": ["col_costura"],
        "descricao": "A costura da lateral abriu e a etiqueta está solta.",
        "arquivo": "col_05.png",
        "resolucao_final": "Costura aberta por defeito de acabamento. Aprovado reparo/troca.",
        "veredito": "procedente",
    },
    # ---------------- Guarda-roupas ----------------
    {
        "numero_chamado": "CH-GR-0001",
        "sku": "GR-6PORTAS",
        "checklist": ["gr_porta"],
        "descricao": "Duas portas ficaram desalinhadas e não fecham direito.",
        "arquivo": "gr_01.png",
        "resolucao_final": "Desalinhamento por regulagem. Agendada visita técnica de ajuste.",
        "veredito": "procedente",
    },
    {
        "numero_chamado": "CH-GR-0002",
        "sku": "GR-6PORTAS",
        "checklist": ["gr_dobradica"],
        "descricao": "Uma dobradiça quebrou e a porta ficou pendurada.",
        "arquivo": "gr_02.png",
        "resolucao_final": "Dobradiça com defeito. Enviado kit de ferragens em garantia.",
        "veredito": "procedente",
    },
    {
        "numero_chamado": "CH-GR-0003",
        "sku": "GR-3PORTAS",
        "checklist": ["gr_mdf"],
        "descricao": "O MDF perto do rodapé inchou, parece que pegou umidade.",
        "arquivo": "gr_03.png",
        "resolucao_final": "Inchaço por exposição a umidade no ambiente do cliente. Garantia recusada.",
        "veredito": "improcedente",
    },
    {
        "numero_chamado": "CH-GR-0004",
        "sku": "GR-3PORTAS",
        "checklist": ["gr_espelho"],
        "descricao": "O espelho da porta veio trincado dentro da embalagem.",
        "arquivo": "gr_04.png",
        "resolucao_final": "Espelho trincado no transporte. Aprovada troca da porta espelhada.",
        "veredito": "procedente",
    },
    {
        "numero_chamado": "CH-GR-0005",
        "sku": "GR-6PORTAS",
        "checklist": ["gr_corredica"],
        "descricao": "A corrediça da gaveta trava e a gaveta não desliza.",
        "arquivo": "gr_05.png",
        "resolucao_final": "Corrediça com defeito de fábrica. Enviada peça em garantia.",
        "veredito": "procedente",
    },
]
