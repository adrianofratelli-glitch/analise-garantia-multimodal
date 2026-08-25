# Análise de Garantia com IA — interface, fluxos e roteiro

> Terceira parte do briefing. A demo tem duas pontas, e as duas precisam estar na tela ao mesmo tempo.

---
## Estado atual — modo palco

O shell tem duas ações: **Abrir chamado** e **Revisar**. Cenários mutuamente
exclusivos são escolhidos em um único seletor; o painel de métricas, o hero
explicativo e o rodapé foram removidos. A tela preserva upload, análise real,
veredito e chegada por Change Stream — a evidência da demo.

## Contrato visual do portfólio (v2)

Esta UI participa da assinatura MongoDB Dark das PoVs. O arquivo
`src/pov-signature.css` é uma cópia sincronizada entre os onze frontends e deve
ser importado **depois** do stylesheet local. O contêiner raiz carrega
`data-pov-shell`, existe um `.pov-skip-link` para `#conteudo-principal` e o
`index.html` declara pt-BR, dark color scheme, theme color e o favicon comum.

A camada compartilhada é dona da document rail, foco, touch targets e redução de
movimento. Este arquivo continua dono do fluxo e das exceções de domínio: não
achate uma tela operacional num template de landing page e não remova a tese
visual específica desta PoV. Qualquer mudança na assinatura precisa ser
replicada nas onze cópias e validada em 1440, 768 e 360 px, além do build de
produção e do estado offline.


## As duas pontas

O cliente que abre o chamado e o analista que revisa. **As duas em janelas diferentes** — é assim que o Change Stream deixa de ser bullet de slide e vira uma coisa que acontece na frente de quem assiste.

Regra que vale pra tudo: **a UI não conclui nada.** Veredito, tipo de defeito, comparação com o catálogo e precedentes vêm todos do backend. O React exibe e organiza.

## Stack

React 18 + Vite + LeafyGreen, JavaScript sem TypeScript, `fetch` cru embrulhado em `api.js`. Sem router, sem biblioteca de estado.

Inclui `@leafygreen-ui/code` — quero mostrar o documento MongoDB cru na tela. Quando o cliente pergunta "mas o que exatamente ficou salvo?", a resposta é abrir o JSON, não descrever.

`nodePolyfills` é obrigatório: `@emotion/server`, dependência transitiva do LeafyGreen, usa builtins do Node.

Portas fixas com `strictPort: true` (Vite em 5190), e o proxy encaminha **duas** rotas pro backend em 8100: `/api` e `/media`. A segunda serve as imagens dos chamados — em produção sairiam do S3 + CDN.

## Estado no shell

`App.jsx` guarda `portalState` e `revisaoState` e passa por props. **As abas não são donas do próprio estado**, por um motivo prático: na demo eu alterno entre Portal e Revisão o tempo todo, e o resultado da análise precisa continuar lá quando eu volto.

O Portal também recebe um `goRevisar`, que troca de aba programaticamente. Depois de analisar um caso, o caminho natural é ir ver ele entrando na fila — sem obrigar ninguém a caçar a aba certa no meio da apresentação.

O shell consulta `/api/health` para conexão e contagens essenciais, mas não
mantém uma barra de estatísticas. Esses números só aparecem no contexto em que
ajudam a interpretar o chamado ou a fila.

## As duas abas

| Aba | O que precisa ficar visível |
|---|---|
| **Portal** | o fluxo do cliente: pedido, checklist, foto, veredito **com os precedentes que o justificaram** |
| **Revisão** | a fila do analista, alimentada ao vivo por Change Stream |

O Portal vai ser o componente maior, e tudo bem: é fluxo de várias etapas, e cada etapa carrega um argumento diferente. O pedido vem do catálogo real, o checklist é derivado da categoria (nada hardcoded), a foto passa por embedding multimodal, e a resposta é estruturada por tool use forçado.

## Componentes

- **`VeredictoCard`** — o resultado estruturado. É o que o cliente do meu cliente veria.
- **`PipelineSteps`** — as etapas do `POST /api/analisar`, em ordem, com `pending → running → done`, cada uma com uma linha curta explicando o que está acontecendo. Sem isso a análise parece uma caixa preta que demora e cospe um texto.
- **`IdentidadeCard`** — o sinal de comparação com o catálogo, **separado do veredito**, mostrando o SKU disputante quando existe. Os dois modos de falha aparecem com textos diferentes, porque a ação do analista é diferente.
- **`JsonViewer`** — o documento cru, quando alguém quiser ver.

O painel de precedentes mostra o `funnel`: quantos candidatos, qual o filtro aplicado, quantos voltaram, e por qual modo (`$rankFusion`, `$vectorSearch` ou fallback). Se eu não conseguir mostrar o afunilamento, "busca vetorial" continua sendo palavra.

## Um detalhe do upload

Separa `upload()` de `request()` no `api.js`, por um motivo específico: **não define `Content-Type` manualmente no multipart.** O browser precisa gerar o boundary sozinho; setar o header na mão quebra o upload de forma silenciosa e chata de diagnosticar.

## A fila ao vivo

`Revisao.jsx` abre um `EventSource` em `/api/chamados/stream`. Do outro lado tem um Change Stream do Atlas.

**É o beat mais forte do roteiro**: duas janelas abertas, eu analiso um caso no Portal, e ele aparece na Revisão sem ninguém recarregar nada.

A fila inicial vem de `/api/chamados/pendentes`; o stream cuida do que chega depois — e o evento é gatilho, não payload, então a fila fica sempre consistente com o banco. O badge "live" reflete o estado real da conexão, não fica verde por otimismo.

## O roteiro que eu preciso conseguir executar no fim

1. **Consultar um pedido real** pelo número. Mostrar que produto, categoria e checklist saem do próprio catálogo — nada hardcoded.
2. **Enviar foto do produto certo com defeito.** Mostrar o veredito estruturado e, principalmente, **os precedentes que o justificaram**. A resposta não é opinião do modelo; é modelo raciocinando sobre casos que a operação já resolveu.
3. **Enviar foto de produto diferente.** O sinal de catálogo acusa antes de qualquer conclusão sobre causa, e aponta com qual SKU aquela foto se parece mais.
4. **Marcar dois itens e mandar uma foto por item.** Cada uma vira embedding próprio, passa pela identidade e chega ao Claude junto da principal.
5. **Mostrar o `funnel`** — o `$rankFusion` combinando vetorial e full-text numa agregação só, com os pesos e o afunilamento visíveis.
6. **Abrir a Revisão em outra janela**, analisar um caso novo e ver ele aparecer na fila ao vivo.
7. **Revisar o caso.** Ele vira `resolvido` e passa a ser candidato a precedente do próximo. O contador do topo sobe na frente do cliente.
8. **Mostrar o validador de schema** recusando um documento fora do contrato.

Um aviso sobre o passo 2: se a foto do seed for uma foto de catálogo sem dano visível, o veredito honesto é **inconclusivo, com confiança baixa**. Isso é comportamento correto e vale mostrar, não é take ruim pra refazer. Um modelo que dá veredito confiante em cima de foto sem defeito é exatamente o que a revisão humana existe pra pegar.

## Antes de apresentar

- Índices vetoriais e o `chamados_text_index` em **READY** — sem o de texto não existe `$rankFusion`.
- Uma análise de aquecimento, pra pagar o cold start de Voyage e Anthropic fora da demo.
- Duas janelas já abertas, Portal e Revisão, antes de começar a falar.
