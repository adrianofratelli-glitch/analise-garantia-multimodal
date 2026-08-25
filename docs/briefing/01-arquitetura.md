# Análise de Garantia com IA — arquitetura e princípios

> Primeira das três partes do briefing desta PoV. O fluxo de análise, as decisões de arquitetura e as regras que não se relaxam. Coleções, índices e busca em `02-mongodb.md`; tela e roteiro em `03-interface-fluxos.md`.

---

## O que eu quero construir

Uma PoV de **triagem de defeito em garantia**, genérica o suficiente pra servir a qualquer varejista que venda produto físico — não amarrada a um cliente específico.

O fluxo do lado do cliente é curto: procura o pedido, marca um checklist de defeito, descreve o problema, envia uma foto (e, se quiser, uma foto por item marcado). O Claude classifica a causa provável usando **precedentes históricos** recuperados por busca vetorial.

Vereditos possíveis: **defeito de fábrica / transporte / mau uso / inconclusivo**.

E sempre marcado pra revisão humana. O CDC exige isso no Brasil, então `revisao_humana` é `true` **por construção, não por configuração** — não faz disso um parâmetro que alguém possa desligar sem querer. O backend seta esse campo depois de receber o veredito, sobrescrevendo o que vier do modelo.

## O argumento comercial em oito linhas

Essa tabela é a PoV inteira. Quero que ela seja verdadeira no código, não só no README:

| Camada | Onde vive |
|---|---|
| Consulta de pedido | coleção `pedidos` |
| Catálogo de checklist de defeito | coleção `catalogo` |
| Casos + veredito + embedding | coleção `chamados` |
| Busca semântica | Atlas Vector Search (`$vectorSearch`) |
| Busca híbrida | `$rankFusion` (vetor + Atlas Search full-text) |
| Verificação de identidade do produto | `$vectorSearch` sobre `catalogo_fotos` |
| Fila de revisão ao vivo | Change Streams via SSE, **sem polling** |
| Analytics | Aggregation Pipeline |
| Governança de schema | validador `$jsonSchema` em `chamados` e `pedidos` |

**Um cluster.** Nenhum vector DB separado, nenhum motor de busca separado, nenhuma fila separada. Se em algum momento você sentir vontade de adicionar Redis, Elastic ou uma fila, para e me pergunta — provavelmente é sinal de que a modelagem está errada, não de que falta componente.

## Imagem nunca entra no MongoDB

Blob vai pra disco local no PoV (`backend/media/`, servido por static files do FastAPI). Em produção troca-se `storage.py` por S3 + CDN **atrás do mesmo contrato de retorno `(uri, url)`**.

**Não muda essa interface.** Ela existe pra que a migração pra produção seja um arquivo, e não um refactor. Todo chamador só conhece `(uri, url)`: a `uri` (`file://<key>`) é o que persiste no documento, a `url` (`/media/<key>`) é o que vai no `<img src>`.

E o `storage.py` valida path traversal por conta própria: resolve o caminho, confirma que ele está **abaixo** do `MEDIA_ROOT`, e recusa qualquer outra coisa. Sim, a key é montada pelo backend hoje — mas ela carrega o id do item de checklist que veio do cliente, e "hoje é seguro" não é argumento pra deixar sem checagem.

## Tudo parametrizado por `.env`

Nome de database, de coleção, de índice, de modelo, limite de imagem, timeout de query — tudo. Lido uma vez por `backend/config.py`, que sobe a árvore de diretórios procurando o `.env`.

**Nunca hardcoda nome de coleção, índice ou modelo.** Se precisar de um novo, adiciona em `config.py` + `.env.example`. Já perdi tempo caçando um nome de índice cravado no meio de um módulo.

As fotos de seed **não vão pro repositório**. Quem roda a PoV aponta `SEED_IMAGES_DIR` pra uma pasta própria. Foto de produto de cliente num repo público é o tipo de coisa que ninguém repara até reparar.

## O fluxo de análise — `POST /api/analisar`

Oito passos, nessa ordem:

1. **Resolve o produto** em `pedidos` por `numero_pedido` + `sku`, e daí tira a `categoria`.
2. **Valida a entrada contra o catálogo**, não contra uma lista no código: item de checklist desconhecido, item duplicado, descrição fora do limite, foto extra a mais, ou foto extra referenciando item que não foi marcado — tudo isso é 422 antes de qualquer chamada paga.
3. **Normaliza a imagem pra JPEG** com Pillow. Isso é deliberado: mantém o `media_type` consistente com os bytes e garante um formato que a vision API do Claude aceita. Evita 400 por PNG, WebP ou content-type divergente. **O mesmo JPEG normalizado vai pro storage, pra Voyage e pro Claude** — não regera em cada etapa. E dá `thumbnail((1568, 1568))` antes de salvar: 1568 é o teto que a visão do Claude usa, e acima disso a API redimensiona do lado dela **cobrando os tokens da imagem cheia**.
4. **Compõe uma frase natural** a partir do checklist + descrição (`compor_frase`).
5. **Sobe a imagem** via `storage.upload_imagem` → `(uri, url)`.
6. **Gera o embedding multimodal** com Voyage `voyage-multimodal-3.5` (1024d), a partir da frase + imagem PIL.
7. **Recupera precedentes** — `vector_search` ou `hybrid_search` com `$rankFusion`. Filtro: `{categoria, status: resolvido}`.
8. **Pede o veredito** ao Claude com **tool use FORÇADO**, e **insere o caso completo** (com embedding) em `chamados`, com `status: em_analise`.

### Paralelismo, porque o caminho crítico importa

Esse endpoint chama Voyage, Atlas e Anthropic. Em série, dá pra sentir a espera numa apresentação. Então:

- O **upload da imagem sai como task paralela** (`asyncio.create_task` + `run_in_threadpool`) e só é aguardado na montagem da resposta. Ele não pertence ao caminho crítico embedding → RAG → veredito.
- A **verificação de identidade e a busca de precedentes** rodam juntas num `asyncio.gather`, porque são duas consultas independentes sobre o mesmo vetor.
- Se qualquer coisa falhar no meio, **cancela as tasks de upload** antes de levantar o erro. Task órfã escrevendo arquivo depois que a requisição já morreu é bug chato de reproduzir.

### As fotos extras não são enfeite

Cada item de checklist marcado pode receber uma foto própria. E elas **não são só evidência guardada**: cada uma gera o próprio embedding multimodal, roda a própria verificação de identidade, e vai junto da foto principal pro Claude no veredito, cada uma rotulada com o item a que se refere.

Na identidade, **o mais restritivo vence**: se qualquer foto divergir do SKU, o chamado inteiro fica sinalizado.

### Por que o veredito usa tool use forçado

Porque parse de JSON em cima de texto livre de LLM quebra em produção, sempre. Com `tool_choice={"type": "tool", "name": "emitir_veredito"}` a saída é estruturada por contrato do modelo — não existe "às vezes ele coloca uma crase a mais" nem "às vezes ele explica antes do JSON". O SDK devolve `block.input` já como dict validado contra o `input_schema`.

Não implementa um caminho alternativo que faça parse de texto. Se o tool call falhar, é erro, não é fallback.

Depois de receber, o backend impõe as invariantes: `confianca` clampada em 0.0–1.0 (mesmo se vier lixo ou string), `sinais_observados` com default, `revisao_humana = True` sempre, e um `_meta` com modelo, latência, tokens (inclusive cache read/write) e quantos precedentes foram usados. Esse `_meta` alimenta o `/api/analytics` depois — se você não gravar, a página de analytics vira estimativa.

E marca `cache_control: ephemeral` no system prompt e no schema da tool: os dois são idênticos em toda análise, e sem isso você paga uns 250 tokens de entrada novos a cada foto enviada.

### O ciclo de aprendizado — e é aqui que está o valor

`POST /api/revisar` vira o `status` pra `resolvido` e seta `veredito.revisao_humana=True`.

**É isso, e só isso, que torna um caso elegível como precedente futuro.** O filtro `{status: resolvido}` no passo 7 garante que nenhum veredito não-revisado contamine a base.

O update é condicionado a `status: "em_analise"`, então revisão duplicada não sobrescreve: se o chamado existe mas já foi revisado, responde **409**; se não existe, **404**. Sem isso, dois analistas na fila ao mesmo tempo sobrescrevem a decisão um do outro em silêncio.

O efeito prático que eu quero mostrar em cliente: o sistema fica melhor conforme os analistas trabalham, sem retreino, sem pipeline, sem nada além do trabalho que a operação já faz todo dia.

## A comparação com o catálogo é um sinal SEPARADO

Antes da classificação, compara a foto enviada contra as fotos de referência do catálogo (`catalogo_fotos`), com o mesmo embedding multimodal + `$vectorSearch`.

Esse sinal responde uma pergunta **diferente** da causa do defeito: *"o cliente está fotografando o produto que ele comprou?"*.

**Mantém separado do veredito.** Misturar os dois faria uma foto errada virar "mau uso" — que é uma conclusão bem diferente de "produto trocado", e é o tipo de erro que gera reclamação no Procon. Na tela, os dois sinais também ficam em cards separados; a separação visual é a tradução da decisão de backend.

O critério de decisão está em `02-mongodb.md`, e ele é **relativo, medido, não absoluto** — leia antes de mexer.

## Tratamento de erro — uma via só

Toda chamada ao banco passa por `db.safe_query(...)`, que embrulha exceção em `SafeQueryError(kind, message)`. Um único `@app.exception_handler(SafeQueryError)` converte isso em 503 com corpo `{"error": {"kind", "message"}}`, que o frontend renderiza como Banner.

**Falha de domínio também levanta `SafeQueryError` direto** — pedido não encontrado, SKU inválido, imagem inválida, embedding que falhou, Claude que não respondeu. Não inventa um caminho de erro paralelo pra esses casos. Validação de formato de entrada (tamanho, duplicata, item desconhecido) é `HTTPException` 422, que é outra coisa: erro do cliente, não falha de dependência.

Isso não é capricho de arquitetura. A análise depende de Voyage, Anthropic e Atlas ao mesmo tempo; mensagem genérica de erro numa demo com cliente custa cinco minutos de improviso. Erro específico deixa óbvio onde olhar — o `kind` diz qual das três caiu.

Um detalhe bom: "pedido não encontrado" devolve **a lista dos pedidos que existem**. Numa demo, o cliente digita errado, e a mensagem já resolve sozinha em vez de virar tentativa e erro na minha frente.

No frontend, a falha de rede tem texto próprio: *"Backend não respondeu. O FastAPI está rodando na porta 8100?"*.

## Backend

`main.py` só com rotas. Toda lógica delegada aos módulos:

| Módulo | Papel |
|---|---|
| `db.py` | cliente Motor, acessores de coleção, `safe_query`/`SafeQueryError` |
| `rag.py` | `vector_search`, `hybrid_search`, `verificar_identidade` |
| `voyage.py` | wrapper de `embed_multimodal` |
| `llm.py` | Claude com tool use forçado, devolve veredito estruturado |
| `storage.py` | blob de imagem — **troca ESTE arquivo, não os chamadores**, pra ir de disco a S3 |
| `defeitos_catalog.py` | checklist → frase natural, derivação de `tipo_defeito` |
| `observability.py` | log estruturado (`LOG_JSON=1`), request-id em toda resposta, `GET /api/metrics`, `/metrics` Prometheus |
| `setup_indexes.py` | todos os índices e validadores, com nomes do `.env` |

`db.safe_query` loga antes de mapear cada exceção do Mongo pra `SafeQueryError` — quero rastro, não só a mensagem que chegou na tela. E toda query carrega `maxTimeMS` do `.env`: query que pendura na demo é pior que query que falha rápido.

O `compor_frase` e o `derivar_tipo_defeito` são **contrato de consistência entre seed e runtime**. A frase que foi embedada no seed precisa ser montada exatamente pela mesma função que monta a frase em runtime, senão o espaço vetorial do precedente não é o mesmo espaço da consulta e a recuperação degrada sem dar erro nenhum.

## Como rodar

```bash
cd backend
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python seed_meta.py            # pedidos + catalogo
./.venv/bin/python seed.py                 # chamados resolvidos (embeda as imagens deles)
./.venv/bin/python seed_catalogo_fotos.py  # fotos de referência por SKU
./.venv/bin/python setup_indexes.py        # regulares + vetoriais + text search + validadores

./start.sh                                 # backend :8100 + frontend :5190
```

Smoke test do pipeline completo:

```bash
cd backend && ./.venv/bin/python test_http.py   # lookup -> checklist -> analisar
```

Deixa o `test_http.py` **fora do `pytest`**, sem auto-discovery. Ele é smoke test manual contra um backend rodando, e não pode entrar na suíte automatizada.

Testes e lint:

```bash
cd backend
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/pytest
./.venv/bin/ruff check .
```

A suíte cobre o que dá pra cobrir sem cluster: derivação de `tipo_defeito` e composição de frase (o contrato seed × runtime), validação de entrada, path traversal no storage, e os contadores de `/api/metrics`.

Frontend isolado precisa de `npm install --legacy-peer-deps` — o LeafyGreen tem conflito de peer-dep com a versão atual do React. Deixa isso já embutido no `start.sh` e no `run.sh`, senão eu esqueço.

Docker: `docker build -t mm-garantia .` e `docker run --env-file .env -p 18081:8080 mm-garantia`. Container roda non-root, e em produção o nginx serve o build, adiciona CSP e headers de segurança, e faz o mesmo encaminhamento de `/api` e `/media` — mesma origem, sem CORS.

### Portas

8100 e 5190, escolhidas de propósito pra não colidir com as outras PoVs que rodam em 8000 e 5173-5174 nesta máquina.

`start.sh` e `run.sh` devem **preservar** um processo que já esteja escutando na 8100, não matar. Se eu precisar de restart limpo, eu olho o PID e decido — não quero script derrubando processo alheio por conta própria.

## Como quero que você trabalhe

- Nada de nome de coleção, índice ou modelo hardcoded. Sempre `config.py` + `.env.example`.
- Nada de caminho de erro paralelo. Uma via só, `SafeQueryError`.
- Nada de parse de JSON sobre texto livre de LLM. Tool use forçado ou erro.
- A interface do `storage.py` é contrato. Se você precisar mudar a assinatura, me pergunta antes.
- Imagem nunca vai pro MongoDB, nem "só pra simplificar o PoV".
- O threshold relativo da identidade é medido, não chutado.
- Comentário no código explica **por que**, não o que. Onde tem um número medido, o comentário guarda a medição.

## Ordem de trabalho

1. `config.py`, `db.py` e o `safe_query` — a via única de erro antes de qualquer feature.
2. Seeds de `pedidos` e `catalogo`, e o `setup_indexes.py` com os três tipos de índice e os validadores.
3. Normalização de imagem + `storage.py`, testados isoladamente.
4. `voyage.py` — embedding multimodal funcionando num script solto antes de entrar no fluxo.
5. `rag.py` com `vector_search`, e só depois o `hybrid_search` com `$rankFusion`.
6. `verificar_identidade`, com o catálogo de fotos seedado — e **mede o score de um produto errado antes de escolher o critério**.
7. `llm.py` com tool use forçado.
8. O `POST /api/analisar` amarrando os passos, primeiro em série; paraleliza depois que estiver correto.
9. `POST /api/revisar` e o ciclo de precedente.
10. Change Stream → SSE.
11. Frontend: Portal, depois Revisão.

Deixa o `$rankFusion` pro passo 5 e não antes: se a busca vetorial simples não estiver trazendo precedente decente, híbrido só vai mascarar o problema.

## Fronteiras — não gasta tempo com isso

- Blobs em disco local, não em S3. A troca é um arquivo, atrás do mesmo contrato.
- Sem autenticação. O portal assume um cliente já identificado pelo e-commerce.
- Métricas em processo, resetam no restart.
- Os chamados de seed são sintéticos. A qualidade do precedente em produção depende do volume real de casos revisados — e isso é uma coisa boa de dizer em voz alta, porque mostra que o valor cresce com o uso.
- O embedding multimodal mede semelhança semântica; ele **não detecta defeito**. Quem faz isso é o Claude, com o precedente do lado. Confundir os dois é o erro conceitual mais fácil de cometer aqui.
