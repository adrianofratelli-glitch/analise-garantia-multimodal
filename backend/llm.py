"""Anthropic com visão — triagem de garantia via TOOL USE FORÇADO.

Em vez de pedir JSON em texto e dar parse frágil (json.loads + remover cercas
markdown + fallback), forçamos o Claude a chamar a ferramenta `emitir_veredito`.
O SDK devolve `block.input` já como dict validado contra o input_schema — sem
parsing, sem try/except de JSON quebrado.

Nunca é decisão final: revisao_humana sempre True (risco CDC). O modelo é
conservador por design — na dúvida, "inconclusivo". Modelo/limites vêm do config.
"""

import base64
import time

from anthropic import AsyncAnthropic

import config

client = AsyncAnthropic()  # lê ANTHROPIC_API_KEY do ambiente (config carregou o .env)
MODEL = config.ANTHROPIC_MODEL

SYSTEM = """Voce e um analista de triagem de garantia da MadeiraMadeira.
A partir da foto do produto com defeito, da descricao do cliente e de chamados
historicos semelhantes ja resolvidos, classifique a causa PROVAVEL do defeito.

Voce NAO e a decisao final — e uma triagem que sera revisada por um humano.
Seja conservador: na duvida, use "inconclusivo". Uma unica foto raramente prova
sozinha se foi mau uso vs. defeito de transporte vs. defeito de fabrica — so
afirme o que a imagem efetivamente sustenta. Use os precedentes como apoio,
nao como veredito automatico.

Sempre registre o resultado chamando a ferramenta emitir_veredito."""

VEREDITO_TOOL = {
    "name": "emitir_veredito",
    "description": "Registra o veredito estruturado da triagem de garantia.",
    "input_schema": {
        "type": "object",
        "properties": {
            "classificacao": {
                "type": "string",
                "enum": ["defeito_fabrica", "defeito_transporte", "mau_uso", "inconclusivo"],
                "description": "Causa provável do defeito.",
            },
            "confianca": {
                "type": "number",
                "description": "Confiança de 0.0 a 1.0 na classificação.",
            },
            "racional": {"type": "string", "description": "1-2 frases objetivas justificando."},
            "sinais_observados": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Sinais visuais concretos observados na imagem.",
            },
        },
        "required": ["classificacao", "confianca", "racional", "sinais_observados"],
    },
}

_FALLBACK = {
    "classificacao": "inconclusivo",
    "confianca": 0.0,
    "racional": "O modelo não retornou um veredito estruturado.",
    "sinais_observados": [],
}


def _montar_contexto(precedentes: list[dict]) -> str:
    if not precedentes:
        return "(sem precedentes recuperados — base historica ainda fria)"
    linhas = []
    for p in precedentes:
        linhas.append(
            f"- [score {p.get('score', 0):.3f}] "
            f"{p.get('categoria', '?')}/{p.get('tipo_defeito', '?')}: "
            f"\"{p.get('descricao_cliente', p.get('descricao', ''))}\" "
            f"=> resolvido como: {p.get('resolucao_final', '?')}"
        )
    return "\n".join(linhas)


async def analisar_veredito(
    imagem_bytes: bytes,
    media_type: str,
    frase_analise: str,
    precedentes: list[dict],
) -> dict:
    """Chama o Claude com visão e tool use forçado; retorna o veredito estruturado."""
    contexto = _montar_contexto(precedentes)
    b64 = base64.standard_b64encode(imagem_bytes).decode()
    user_text = (
        f"Descricao do chamado:\n{frase_analise}\n\n"
        f"Chamados historicos semelhantes (resolvidos):\n{contexto}\n\n"
        f"Classifique a causa provavel do defeito visivel na imagem e registre via emitir_veredito."
    )

    start = time.perf_counter()
    resp = await client.messages.create(
        model=MODEL,
        max_tokens=config.ANTHROPIC_MAX_TOKENS,
        temperature=0.2,
        system=SYSTEM,
        tools=[VEREDITO_TOOL],
        tool_choice={"type": "tool", "name": "emitir_veredito"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": user_text},
            ],
        }],
    )
    latency_ms = int((time.perf_counter() - start) * 1000)

    tool_input = next((b.input for b in resp.content if b.type == "tool_use"), None)
    veredito = dict(tool_input) if isinstance(tool_input, dict) else dict(_FALLBACK)

    # invariantes de segurança/negócio
    try:
        veredito["confianca"] = max(0.0, min(1.0, float(veredito.get("confianca", 0.0))))
    except (TypeError, ValueError):
        veredito["confianca"] = 0.0
    veredito.setdefault("sinais_observados", [])
    veredito["revisao_humana"] = True
    veredito["_meta"] = {
        "model": resp.model,
        "latency_ms": latency_ms,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "precedentes_usados": len(precedentes),
    }
    return veredito
