import { useEffect, useState } from 'react';
import Badge from '@leafygreen-ui/badge';
import Banner from '@leafygreen-ui/banner';
import Button from '@leafygreen-ui/button';
import TextInput from '@leafygreen-ui/text-input';
import JsonViewer from '../components/JsonViewer.jsx';
import VeredictoCard from '../components/VeredictoCard.jsx';
import { api } from '../api.js';

// Sugestoes de resolucao por classificacao da IA — o humano confirma/edita.
const SUGESTAO = {
  defeito_fabrica: 'Troca aprovada — defeito de fabrica confirmado.',
  defeito_transporte: 'Reenvio aprovado — avaria de transporte confirmada.',
  mau_uso: 'Garantia negada — caracterizado mau uso pelo cliente.',
  inconclusivo: 'Solicitar mais fotos ao cliente — analise inconclusiva.',
};

export default function Revisao({ state, setState }) {
  const { pendentes, selecionado } = state;
  const [resolucao, setResolucao] = useState('');
  const [busy, setBusy] = useState(false);
  const [carregando, setCarregando] = useState(false);
  const [error, setError] = useState(null);
  const [ok, setOk] = useState(null);

  const [live, setLive] = useState(false);

  const carregar = async () => {
    setCarregando(true);
    setError(null);
    try {
      const lista = await api.pendentes();
      setState((s) => ({ ...s, pendentes: lista }));
    } catch (e) {
      setError(e.message);
    } finally {
      setCarregando(false);
    }
  };

  useEffect(() => {
    carregar();
  }, []);

  // Change Streams (SSE) — fila atualiza sozinha quando um novo chamado chega,
  // sem polling. Demonstra real-time operacional nativo do MongoDB.
  useEffect(() => {
    const es = new EventSource('/api/chamados/stream');
    es.onopen = () => setLive(true);
    es.onerror = () => setLive(false);
    es.onmessage = () => carregar();
    return () => es.close();
  }, []);

  const selecionar = (c) => {
    setOk(null);
    setError(null);
    setState((s) => ({ ...s, selecionado: c }));
    setResolucao(SUGESTAO[c.veredito?.classificacao] || '');
  };

  const confirmar = async () => {
    if (!resolucao.trim()) {
      setError('Escreva a resolucao final antes de confirmar.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const doc = await api.revisar(selecionado.numero_chamado, resolucao.trim());
      setOk(`Chamado ${doc.numero_chamado} resolvido e adicionado a base de precedentes.`);
      setState((s) => ({
        ...s,
        selecionado: null,
        pendentes: s.pendentes.filter((p) => p.numero_chamado !== doc.numero_chamado),
      }));
      setResolucao('');
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      {error && <Banner variant="warning" darkMode>{error}</Banner>}
      {ok && <Banner variant="success" darkMode>{ok}</Banner>}

      <div className="two-col">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Fila de revisao humana</span>
            <Button darkMode size="small" onClick={carregar} disabled={carregando}>
              {carregando ? 'Atualizando…' : '↻ Atualizar'}
            </Button>
          </div>
          <div className="dim" style={{ marginBottom: 12 }}>
            Chamados em <b>em_analise</b> aguardando confirmacao. Cada resolucao vira
            precedente recuperavel (flywheel).{' '}
            <Badge variant={live ? 'green' : 'lightgray'}>
              {live ? '● live — Change Streams' : '○ live indisponivel'}
            </Badge>
          </div>
          {(pendentes ?? []).length === 0 && (
            <p className="dim">Nenhum chamado pendente. Abra um no Portal de Garantia.</p>
          )}
          {(pendentes ?? []).map((c) => (
            <button
              key={c.numero_chamado}
              className={`rev-item ${selecionado?.numero_chamado === c.numero_chamado ? 'active' : ''}`}
              onClick={() => selecionar(c)}
            >
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="rev-num">{c.numero_chamado}</span>
                <Badge variant="blue">{c.veredito?.classificacao ?? '—'}</Badge>
              </div>
              <div className="dim" style={{ marginTop: 4 }}>
                {c.produto?.nome} · {c.categoria} · pedido {c.numero_pedido}
              </div>
            </button>
          ))}
        </div>

        <div className="stack">
          {!selecionado && (
            <div className="card">
              <p className="dim">Selecione um chamado na fila para revisar o veredito da IA.</p>
            </div>
          )}
          {selecionado && (
            <>
              <VeredictoCard veredito={selecionado.veredito} />
              <div className="card">
                <div className="card-title" style={{ marginBottom: 8 }}>
                  Resolucao final (humano)
                </div>
                <div className="dim mono" style={{ marginBottom: 10, fontSize: 12 }}>
                  {selecionado.frase_analise}
                </div>
                <TextInput
                  darkMode
                  label="Decisao confirmada"
                  placeholder="Descreva a resolucao definitiva…"
                  value={resolucao}
                  onChange={(e) => setResolucao(e.target.value)}
                />
                <div style={{ marginTop: 12 }}>
                  <Button darkMode variant="primary" onClick={confirmar} disabled={busy}>
                    {busy ? 'Confirmando…' : '✓ Confirmar resolucao'}
                  </Button>
                </div>
              </div>
              <div className="card">
                <div className="card-title" style={{ marginBottom: 8 }}>Documento do chamado</div>
                <JsonViewer doc={selecionado} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
