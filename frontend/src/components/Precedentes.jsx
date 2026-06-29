import { useState } from 'react';
import Badge from '@leafygreen-ui/badge';
import JsonViewer from './JsonViewer.jsx';

const VEREDITO_VAR = {
  procedente: 'green',
  improcedente: 'red',
  inconclusivo: 'yellow',
};

/** Painel de precedentes recuperados pelo $vectorSearch — score visível + JSON. */
export default function Precedentes({ precedentes }) {
  const [aberto, setAberto] = useState(null);

  if (!precedentes || precedentes.length === 0) {
    return <div className="dim">Nenhum precedente recuperado para esta categoria.</div>;
  }

  return (
    <div className="precedentes">
      {precedentes.map((p, i) => {
        const score = typeof p.score === 'number' ? p.score : 0;
        const pct = Math.round(score * 100);
        const isOpen = aberto === i;
        return (
          <div className="precedente" key={p._id || i}>
            <div className="precedente-head" onClick={() => setAberto(isOpen ? null : i)}>
              <span className="precedente-rank mono">#{i + 1}</span>
              <span className="precedente-num mono">{p.numero_chamado}</span>
              <Badge variant={VEREDITO_VAR[p.veredito] || 'lightgray'}>{p.veredito}</Badge>
              <span className="precedente-score mono">score {score.toFixed(3)}</span>
              <div className="score-track">
                <div className="score-fill" style={{ width: `${pct}%` }} />
              </div>
              <span className="precedente-toggle mono">{isOpen ? '−' : '+'}</span>
            </div>
            <div className="precedente-relato">{p.descricao}</div>
            {isOpen && (
              <div className="precedente-json">
                <JsonViewer doc={p} flashKey={`${p._id}-${isOpen}`} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
