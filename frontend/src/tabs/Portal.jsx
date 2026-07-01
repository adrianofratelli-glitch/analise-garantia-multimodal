import { useState } from 'react';
import Badge from '@leafygreen-ui/badge';
import Banner from '@leafygreen-ui/banner';
import Button from '@leafygreen-ui/button';
import TextInput from '@leafygreen-ui/text-input';
import JsonViewer from '../components/JsonViewer.jsx';
import PipelineSteps from '../components/PipelineSteps.jsx';
import VeredictoCard from '../components/VeredictoCard.jsx';
import { api } from '../api.js';

const STEPS = ['Compor frase', 'Guardar foto (storage)', 'Embed multimodal', '$vectorSearch', 'Claude (visão)', 'Gravar chamado'];

export default function Portal({ state, setState }) {
  const { resultado } = state;
  const [pedido, setPedido] = useState('');
  const [produtos, setProdutos] = useState([]);
  const [produtoSel, setProdutoSel] = useState(null);
  const [itens, setItens] = useState([]);
  const [marcados, setMarcados] = useState({});
  const [descricao, setDescricao] = useState('');
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [pipe, setPipe] = useState(STEPS.map(() => 'pending'));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const setStep = (step) => setState((s) => ({ ...s, step }));

  const buscar = async () => {
    setError(null);
    try {
      const r = await api.lookup(pedido);
      setProdutos(r.produtos);
      setPedido(r.numero_pedido);
      setStep(1);
    } catch (e) { setError(e.message); }
  };

  const escolher = async (p) => {
    setError(null);
    setProdutoSel(p);
    try {
      const r = await api.checklist(p.categoria);
      setItens(r.itens);
      setMarcados({});
      setStep(2);
    } catch (e) { setError(e.message); }
  };

  const toggle = (id) => setMarcados((m) => ({ ...m, [id]: !m[id] }));

  const onFile = (e) => {
    const f = e.target.files?.[0] || null;
    setFile(f);
    setPreview(f ? URL.createObjectURL(f) : null);
  };

  const analisar = async () => {
    if (!file) { setError('Envie a foto do defeito.'); return; }
    setBusy(true);
    setError(null);
    setPipe(STEPS.map(() => 'pending'));
    STEPS.forEach((_, i) => setTimeout(() => setPipe((p) => p.map((s, j) => (j < i ? 'done' : j === i ? 'running' : 'pending'))), i * 350));
    const fd = new FormData();
    fd.append('imagem', file);
    fd.append('numero_pedido', pedido);
    fd.append('sku', produtoSel.sku);
    fd.append('descricao', descricao);
    Object.entries(marcados).filter(([, v]) => v).forEach(([k]) => fd.append('checklist', k));
    try {
      const r = await api.analisar(fd);
      setPipe(STEPS.map(() => 'done'));
      setState((s) => ({ ...s, resultado: r, step: 4 }));
    } catch (e) {
      setError(e.message);
      setPipe(STEPS.map(() => 'pending'));
    } finally { setBusy(false); }
  };

  const reiniciar = () => {
    setProdutos([]); setProdutoSel(null); setItens([]); setMarcados({});
    setDescricao(''); setFile(null); setPreview(null); setPedido('');
    setPipe(STEPS.map(() => 'pending'));
    setState({ resultado: null, step: 0 });
  };

  const steps = STEPS.map((title, i) => ({ key: title, index: i + 1, title, status: pipe[i], runningLabel: 'processando…', content: null }));

  return (
    <div className="stack">
      {error && <Banner variant="warning" darkMode>{error}</Banner>}

      <div className="card">
        <div className="card-title" style={{ marginBottom: 12 }}>Portal do cliente — abrir chamado de garantia</div>

        <div className="row" style={{ alignItems: 'flex-end', gap: 12 }}>
          <div style={{ minWidth: 240 }}>
            <TextInput darkMode label="Número do pedido" placeholder="MM-90001" value={pedido}
              onChange={(e) => setPedido(e.target.value)} />
          </div>
          <Button darkMode variant="primary" onClick={buscar} disabled={!pedido.trim()}>Buscar pedido</Button>
          {resultado && <Button darkMode onClick={reiniciar}>Novo chamado</Button>}
        </div>

        {produtos.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div className="dim" style={{ marginBottom: 6 }}>Produtos do pedido — selecione o item com defeito:</div>
            <div className="row">
              {produtos.map((p) => (
                <Button key={p.sku} darkMode size="small"
                  variant={produtoSel?.sku === p.sku ? 'primary' : 'default'}
                  onClick={() => escolher(p)}>{p.nome} · {p.sku}</Button>
              ))}
            </div>
          </div>
        )}

        {itens.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div className="dim" style={{ marginBottom: 6 }}>Checklist da categoria <b>{produtoSel.categoria}</b>:</div>
            <div className="row">
              {itens.map((it) => (
                <label key={it.id} className={`check-chip ${marcados[it.id] ? 'on' : ''}`}>
                  <input type="checkbox" checked={!!marcados[it.id]} onChange={() => toggle(it.id)} />
                  {it.id} <Badge variant="lightgray">{it.tipo}</Badge>
                </label>
              ))}
            </div>
            <div style={{ marginTop: 12 }}>
              <TextInput darkMode label="Descrição livre do cliente" placeholder="Conte o que aconteceu…"
                value={descricao} onChange={(e) => setDescricao(e.target.value)} />
            </div>
            <div style={{ marginTop: 12 }} className="row">
              <input type="file" accept="image/*" onChange={onFile} />
              {preview && <img src={preview} alt="prévia" className="foto-preview" />}
            </div>
            <div style={{ marginTop: 12 }}>
              <Button darkMode variant="primary" onClick={analisar} disabled={busy || !file}>
                {busy ? 'Analisando…' : '▶ Analisar defeito'}
              </Button>
            </div>
          </div>
        )}
      </div>

      {(busy || resultado) && (
        <div className="two-col">
          <div className="card">
            <div className="card-title" style={{ marginBottom: 8 }}>Pipeline (Caminho B)</div>
            <PipelineSteps steps={steps} />
            {resultado && (
              <div className="dim mono" style={{ marginTop: 10, fontSize: 12 }}>
                chamado <b>{resultado.numero_chamado}</b> · status em_analise<br />
                frase: {resultado.frase_analise}
              </div>
            )}
          </div>
          <div className="stack">
            {resultado?.veredito && <VeredictoCard veredito={resultado.veredito} />}
            {resultado?.imagem_url && (
              <div className="card"><div className="card-title" style={{ marginBottom: 8 }}>Foto do cliente</div>
                <img src={resultado.imagem_url} alt="defeito" className="foto-full" /></div>
            )}
          </div>
        </div>
      )}

      {resultado?.precedentes && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">Precedentes recuperados ($vectorSearch)</span>
            <Badge variant="green">{resultado.funnel?.retrieved ?? 0} de {resultado.funnel?.num_candidates} candidatos</Badge>
          </div>
          {resultado.precedentes.map((p) => (
            <div key={p._id} className="prec-item">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="mono">{p.numero_chamado} · {p.categoria}/{p.tipo_defeito}</span>
                <Badge variant="green">score {Number(p.score).toFixed(3)}</Badge>
              </div>
              <JsonViewer doc={p} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
