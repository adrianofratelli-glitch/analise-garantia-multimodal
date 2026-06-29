import Badge from '@leafygreen-ui/badge';

const VARIANTE = {
  procedente: 'green',
  improcedente: 'red',
  inconclusivo: 'yellow',
};

const ROTULO = {
  procedente: 'Procedente',
  improcedente: 'Improcedente',
  inconclusivo: 'Inconclusivo',
};

/** Card de veredito: badge + barra de confiança + aviso de revisão humana. */
export default function VereditoCard({ veredito }) {
  if (!veredito) return null;
  const conf = Math.round((veredito.confianca ?? 0) * 100);

  return (
    <div className="card veredito-card">
      <div className="card-header">
        <span className="card-title">Veredito sugerido</span>
        <Badge variant={VARIANTE[veredito.classificacao] || 'lightgray'}>
          {ROTULO[veredito.classificacao] || veredito.classificacao}
        </Badge>
      </div>

      <div className="conf-row">
        <span className="dim mono">confiança</span>
        <div className="conf-track">
          <div
            className={`conf-fill ${veredito.classificacao}`}
            style={{ width: `${conf}%` }}
          />
        </div>
        <span className="conf-num mono">{conf}%</span>
      </div>

      <div className="veredito-bloco">
        <div className="veredito-label mono">justificativa</div>
        <p className="veredito-text">{veredito.justificativa}</p>
      </div>

      <div className="veredito-bloco">
        <div className="veredito-label mono">recomendação</div>
        <p className="veredito-text">{veredito.recomendacao}</p>
      </div>

      <div className="aviso-revisao">
        ⚠️ Sugestão gerada por IA ({veredito.modelo || 'claude-opus-4-8'}) —
        sujeita a revisão humana antes de qualquer decisão.
      </div>
    </div>
  );
}
