import { useEffect, useRef, useState } from 'react';
import Badge from '@leafygreen-ui/badge';
import Banner from '@leafygreen-ui/banner';
import Button from '@leafygreen-ui/button';
import TextInput from '@leafygreen-ui/text-input';
import { api } from './api.js';
import PipelineSteps from './components/PipelineSteps.jsx';
import JsonViewer from './components/JsonViewer.jsx';
import VereditoCard from './components/VereditoCard.jsx';
import Precedentes from './components/Precedentes.jsx';

const STEPS = ['Pedido', 'Produto', 'Checklist & Relato', 'Foto', 'Resultado'];

// As 6 etapas do pipeline server-side (mesma narrativa do /analisar).
const PIPELINE = [
  { key: 'frase', title: 'Compor frase de análise' },
  { key: 's3', title: 'Subir foto pro S3' },
  { key: 'embed', title: 'Embedding multimodal (Voyage)' },
  { key: 'search', title: '$vectorSearch no Atlas' },
  { key: 'claude', title: 'Veredito do Claude (visão)' },
  { key: 'gravar', title: 'Gravar chamado (em_analise)' },
];

const CATEGORIA_LABEL = {
  cadeira: 'Cadeira',
  colchao: 'Colchão',
  guarda_roupa: 'Guarda-Roupa',
};

export default function App() {
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // saúde do cluster
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(false);

  // etapa 1 — pedido
  const [numeroPedido, setNumeroPedido] = useState('');
  const [pedido, setPedido] = useState(null);

  // etapa 2 — produto
  const [produto, setProduto] = useState(null);

  // etapa 3 — checklist + relato
  const [checklistItens, setChecklistItens] = useState([]);
  const [checked, setChecked] = useState({});
  const [descricao, setDescricao] = useState('');

  // etapa 4 — foto
  const [imagem, setImagem] = useState(null);
  const [preview, setPreview] = useState(null);

  // etapa 5 — resultado
  const [pipe, setPipe] = useState(initPipe('pending'));
  const [analise, setAnalise] = useState(null);
  const pipeTimer = useRef(null);

  // revisão
  const [resolucao, setResolucao] = useState('');
  const [revisado, setRevisado] = useState(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const h = await api.health();
        if (alive) {
          setHealth(h);
          setHealthError(false);
        }
      } catch {
        if (alive) setHealthError(true);
      }
    };
    tick();
    const id = setInterval(tick, 10_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  function initPipe(status) {
    return PIPELINE.map((p, i) => ({ ...p, index: i + 1, status }));
  }

  function reset() {
    clearTimeout(pipeTimer.current);
    setStep(0);
    setNumeroPedido('');
    setPedido(null);
    setProduto(null);
    setChecklistItens([]);
    setChecked({});
    setDescricao('');
    setImagem(null);
    setPreview(null);
    setPipe(initPipe('pending'));
    setAnalise(null);
    setResolucao('');
    setRevisado(null);
    setError(null);
  }

  // ---- etapa 1 ----
  const buscarPedido = async () => {
    if (!numeroPedido.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const p = await api.lookup(numeroPedido.trim());
      setPedido(p);
      setStep(1);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  // ---- etapa 2 -> 3 ----
  const escolherProduto = async (prod) => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.checklist(prod.categoria);
      setProduto(prod);
      setChecklistItens(r.itens);
      setChecked({});
      setStep(2);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  // ---- etapa 4 — foto ----
  const onFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setImagem(f);
    setPreview(URL.createObjectURL(f));
  };

  // ---- etapa 5 — análise ----
  const analisar = async () => {
    if (!imagem) return;
    setBusy(true);
    setError(null);
    setRevisado(null);
    setAnalise(null);
    setStep(4);

    // anima o pipeline enquanto o request roda (progresso simulado)
    setPipe(initPipe('pending'));
    let i = 0;
    const advance = () => {
      setPipe((prev) =>
        prev.map((p, idx) => ({
          ...p,
          status: idx < i ? 'done' : idx === i ? 'running' : 'pending',
        })),
      );
      i += 1;
      if (i < PIPELINE.length) {
        pipeTimer.current = setTimeout(advance, 800);
      }
    };
    advance();

    try {
      const r = await api.analisar({
        imagem,
        numero_pedido: pedido.numero_pedido,
        sku: produto.sku,
        checklist: Object.keys(checked).filter((k) => checked[k]),
        descricao,
      });
      clearTimeout(pipeTimer.current);
      setPipe(pipeContent(r));
      setAnalise(r);
      setResolucao(r.veredito?.recomendacao || '');
    } catch (e) {
      clearTimeout(pipeTimer.current);
      setPipe((prev) => prev.map((p) => ({ ...p, status: p.status === 'running' ? 'pending' : p.status })));
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  function pipeContent(r) {
    const f = r.funnel || {};
    const content = {
      frase: <span className="dim mono small">{r.frase_analise}</span>,
      s3: <span className="dim mono small">imagem enviada ao S3</span>,
      embed: <span className="dim mono small">vetor 1024-d (input_type=query)</span>,
      search: (
        <span className="dim mono small">
          {f.recuperados}/{f.limit} precedentes · {f.num_candidates} candidatos · melhor score{' '}
          {f.melhor_score ?? '—'}
        </span>
      ),
      claude: (
        <span className="dim mono small">
          {r.veredito?.classificacao} · {Math.round((r.veredito?.confianca ?? 0) * 100)}%
        </span>
      ),
      gravar: <span className="dim mono small">{r.numero_chamado} (em_analise)</span>,
    };
    return PIPELINE.map((p, idx) => ({ ...p, index: idx + 1, status: 'done', content: content[p.key] }));
  }

  // ---- revisão ----
  const confirmarRevisao = async () => {
    if (!resolucao.trim() || !analise) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.revisar(analise.numero_chamado, resolucao.trim());
      setRevisado(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const checkedIds = Object.keys(checked).filter((k) => checked[k]);

  return (
    <>
      <nav className="top-nav">
        <div className="nav-inner">
          <span className="nav-logo">
            <span className="leaf">●</span> MM Análise de Garantia
          </span>
          <div className="nav-pills">
            {STEPS.map((name, i) => (
              <button
                key={name}
                className={`nav-pill ${i === step ? 'active' : ''} ${i < step ? 'feito' : ''}`}
                onClick={() => i <= step && setStep(i)}
                disabled={i > step}
              >
                {i + 1}. {name}
              </button>
            ))}
          </div>
          <span className="status-pill">
            <span className={`status-dot ${healthError || !health ? 'err' : 'ok'}`} />
            {healthError ? 'sem conexão' : health ? 'Atlas · ping ok' : 'conectando…'}
          </span>
        </div>
      </nav>

      <main className="content">
        <div className="hero-kicker">PoV · MadeiraMadeira</div>
        <h1 className="page-title">
          Garantia analisada com <span>foto + precedentes</span>
        </h1>
        <p className="page-subtitle">
          Embedding multimodal (Voyage) + $vectorSearch no MongoDB Atlas + visão do Claude.
          A foto e a frase do chamado recuperam casos resolvidos parecidos; o veredito é
          uma sugestão sujeita a revisão humana.
        </p>

        {error && (
          <Banner variant="warning" darkMode onClose={() => setError(null)}>
            {error}
          </Banner>
        )}

        <div className="spacer" />

        {/* ETAPA 1 — PEDIDO */}
        {step === 0 && (
          <div className="card fade-in">
            <div className="card-header">
              <span className="card-title">1 · Informe o número do pedido</span>
            </div>
            <div className="row">
              <div style={{ flex: 1, minWidth: 240 }}>
                <TextInput
                  darkMode
                  aria-label="número do pedido"
                  placeholder="ex.: MM-100234"
                  value={numeroPedido}
                  onChange={(e) => setNumeroPedido(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && buscarPedido()}
                />
              </div>
              <Button darkMode variant="primary" onClick={buscarPedido} disabled={busy}>
                {busy ? 'Buscando…' : 'Buscar pedido'}
              </Button>
            </div>
            <div className="dim small" style={{ marginTop: 10 }}>
              Pedidos de exemplo: MM-100234, MM-100871, MM-101502, MM-101990
            </div>
          </div>
        )}

        {/* ETAPA 2 — PRODUTO */}
        {step === 1 && pedido && (
          <div className="card fade-in">
            <div className="card-header">
              <span className="card-title">2 · Escolha o produto com defeito</span>
              <Badge variant="blue">{pedido.numero_pedido}</Badge>
            </div>
            <div className="dim small" style={{ marginBottom: 12 }}>
              Cliente: {pedido.cliente} · Data: {pedido.data}
            </div>
            <div className="produtos-grid">
              {pedido.produtos.map((p) => (
                <button key={p.sku} className="produto-card" onClick={() => escolherProduto(p)} disabled={busy}>
                  <div className="produto-nome">{p.nome}</div>
                  <div className="produto-sku mono">{p.sku}</div>
                  <Badge variant="lightgray">{CATEGORIA_LABEL[p.categoria] || p.categoria}</Badge>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ETAPA 3 — CHECKLIST + RELATO */}
        {step === 2 && produto && (
          <div className="card fade-in">
            <div className="card-header">
              <span className="card-title">3 · Marque os defeitos e descreva o problema</span>
              <Badge variant="green">{produto.sku}</Badge>
            </div>
            <div className="checklist">
              {checklistItens.map((item) => (
                <label key={item.id} className="check-row">
                  <input
                    type="checkbox"
                    checked={!!checked[item.id]}
                    onChange={(e) => setChecked((c) => ({ ...c, [item.id]: e.target.checked }))}
                  />
                  <span>{item.label}</span>
                </label>
              ))}
            </div>
            <div className="spacer" />
            <label className="field-label">Relato do cliente</label>
            <textarea
              className="ta"
              placeholder="Descreva o problema com as palavras do cliente…"
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
            />
            <div className="row" style={{ marginTop: 16, justifyContent: 'flex-end' }}>
              <Button darkMode onClick={() => setStep(1)}>◀ Voltar</Button>
              <Button
                darkMode
                variant="primary"
                onClick={() => setStep(3)}
                disabled={checkedIds.length === 0 && !descricao.trim()}
              >
                Próximo: enviar foto ▶
              </Button>
            </div>
          </div>
        )}

        {/* ETAPA 4 — FOTO */}
        {step === 3 && produto && (
          <div className="card fade-in">
            <div className="card-header">
              <span className="card-title">4 · Envie a foto do defeito</span>
              <Badge variant="green">{produto.sku}</Badge>
            </div>
            <label className="upload-drop">
              <input type="file" accept="image/*" onChange={onFile} hidden />
              {preview ? (
                <img src={preview} alt="prévia" className="upload-preview" />
              ) : (
                <span className="dim">Clique para selecionar uma imagem do produto</span>
              )}
            </label>
            <div className="row" style={{ marginTop: 16, justifyContent: 'flex-end' }}>
              <Button darkMode onClick={() => setStep(2)}>◀ Voltar</Button>
              <Button darkMode variant="primary" onClick={analisar} disabled={busy || !imagem}>
                {busy ? 'Analisando…' : 'Analisar garantia ▶'}
              </Button>
            </div>
          </div>
        )}

        {/* ETAPA 5 — RESULTADO */}
        {step === 4 && (
          <div className="fade-in stack">
            <div className="two-col">
              <div className="card">
                <div className="card-header">
                  <span className="card-title">Pipeline da análise</span>
                </div>
                <PipelineSteps steps={pipe} />
                {analise?.funnel && (
                  <>
                    <div className="spacer" />
                    <div className="card-title small">Funil do $vectorSearch</div>
                    <JsonViewer doc={analise.funnel} />
                  </>
                )}
              </div>

              <div className="stack">
                {analise?.imagem_url && (
                  <div className="card">
                    <div className="card-header">
                      <span className="card-title">Foto analisada</span>
                      {analise?.numero_chamado && <Badge variant="blue">{analise.numero_chamado}</Badge>}
                    </div>
                    <img src={analise.imagem_url} alt="chamado" className="foto-analisada" />
                  </div>
                )}
                <VereditoCard veredito={analise?.veredito} />
              </div>
            </div>

            {analise && (
              <div className="card">
                <div className="card-header">
                  <span className="card-title">Precedentes recuperados</span>
                  <Badge variant="lightgray">{analise.precedentes?.length || 0} casos</Badge>
                </div>
                <Precedentes precedentes={analise.precedentes} />
              </div>
            )}

            {/* REVISÃO HUMANA */}
            {analise && (
              <div className="card alt">
                <div className="card-header">
                  <span className="card-title">Revisão humana</span>
                  {revisado && <Badge variant="green">resolvido</Badge>}
                </div>
                {revisado ? (
                  <div className="dim">
                    Chamado <span className="mono">{revisado.numero_chamado}</span> marcado como{' '}
                    <strong>resolvido</strong>. Resolução registrada:
                    <p className="veredito-text" style={{ marginTop: 8 }}>
                      {revisado.chamado?.resolucao_final}
                    </p>
                  </div>
                ) : (
                  <>
                    <label className="field-label">
                      Resolução final (confirme ou ajuste a recomendação da IA)
                    </label>
                    <textarea
                      className="ta"
                      value={resolucao}
                      onChange={(e) => setResolucao(e.target.value)}
                    />
                    <div className="row" style={{ marginTop: 16, justifyContent: 'flex-end' }}>
                      <Button darkMode variant="primary" onClick={confirmarRevisao} disabled={busy || !resolucao.trim()}>
                        {busy ? 'Registrando…' : 'Confirmar resolução'}
                      </Button>
                    </div>
                  </>
                )}
              </div>
            )}

            <div className="row" style={{ justifyContent: 'center' }}>
              <Button darkMode onClick={reset}>↺ Nova análise</Button>
            </div>
          </div>
        )}
      </main>

      <footer className="app-footer">
        <p>MongoDB Atlas · POC.chamados — voyage-multimodal-3 (1024d) · $vectorSearch + Claude opus-4-8</p>
      </footer>
    </>
  );
}
