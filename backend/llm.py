"""Wrapper do Claude (Anthropic) — veredito de garantia com visão.

analisar_veredito() recebe a foto do produto (vision), a frase de análise e os
precedentes recuperados pelo $vectorSearch, e devolve um veredito estruturado:
classificacao, confianca (0-1), justificativa, recomendacao.

Usamos o SDK `anthropic` (ANTHROPIC_API_KEY), modelo claude-opus-4-8, com
thinking adaptativo e structured outputs (output_config.format) — o primeiro
bloco de texto da resposta é JSON válido contra o schema abaixo.
"""

import base64
import json

from anthropic import AsyncAnthropic

MODEL = "claude-opus-4-8"

client = AsyncAnthropic()  # lê ANTHROPIC_API_KEY do ambiente

# Schema do veredito (structured outputs garante JSON válido).
VEREDITO_SCHEMA = {
    "type": "object",
    "properties": {
        "classificacao": {
            "type": "string",
            "enum": ["procedente", "improcedente", "inconclusivo"],
            "description": "Procedente = defeito de fábrica coberto pela garantia; "
            "improcedente = mau uso/dano externo; inconclusivo = a foto não permite decidir.",
        },
        "confianca": {
            "type": "number",
            "description": "Confiança de 0 a 1 na classificação.",
        },
        "justificativa": {
            "type": "string",
            "description": "2 a 4 frases explicando o que a foto evidencia e como os precedentes pesaram.",
        },
        "recomendacao": {
            "type": "string",
            "description": "Próxima ação sugerida ao analista (ex.: aprovar troca, recusar, pedir nova foto).",
        },
    },
    "required": ["classificacao", "confianca", "justificativa", "recomendacao"],
    "additionalProperties": False,
}

SYSTEM = (
    "Você é um analista de garantia da MadeiraMadeira (móveis e colchões). "
    "Avalia chamados de garantia olhando a FOTO do produto, a descrição do "
    "cliente e PRECEDENTES de chamados já resolvidos (recuperados por similaridade). "
    "Classifique o defeito como 'procedente' (defeito de fábrica coberto), "
    "'improcedente' (mau uso ou dano externo) ou 'inconclusivo' (a imagem não "
    "permite decidir). Baseie-se no que a imagem realmente mostra; use os "
    "precedentes como apoio, não como regra absoluta. Seja objetivo: este "
    "veredito é uma sugestão sujeita a revisão humana."
)


def _precedentes_texto(precedentes: list[dict]) -> str:
    """Serializa os precedentes recuperados para injetar no prompt."""
    if not precedentes:
        return "(nenhum precedente recuperado)"
    linhas = []
    for i, p in enumerate(precedentes, 1):
        linhas.append(
            f"[{i}] score={p.get('score', 0):.3f} | veredito={p.get('veredito', '?')} | "
            f"defeito={p.get('tipo_defeito', '?')}\n"
            f"     relato: {p.get('descricao', '')}\n"
            f"     resolução: {p.get('resolucao_final', '')}"
        )
    return "\n".join(linhas)


async def analisar_veredito(
    imagem_bytes: bytes,
    media_type: str,
    frase_analise: str,
    precedentes: list[dict],
) -> dict:
    """Chama o Claude com a imagem (visão) + frase + precedentes.

    Returns:
        dict com classificacao, confianca, justificativa, recomendacao.
    """
    imagem_b64 = base64.standard_b64encode(imagem_bytes).decode("utf-8")

    user_content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": imagem_b64,
            },
        },
        {
            "type": "text",
            "text": (
                f"CHAMADO ATUAL:\n{frase_analise}\n\n"
                f"PRECEDENTES RECUPERADOS (chamados resolvidos, por similaridade):\n"
                f"{_precedentes_texto(precedentes)}\n\n"
                "Analise a foto e emita o veredito estruturado."
            ),
        },
    ]

    resp = await client.messages.create(
        model=MODEL,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        messages=[{"role": "user", "content": user_content}],
        output_config={"format": {"type": "json_schema", "schema": VEREDITO_SCHEMA}},
    )

    # Com output_config.format, o primeiro bloco de texto é JSON válido.
    texto = next((b.text for b in resp.content if b.type == "text"), "")
    veredito = json.loads(texto)
    return veredito
