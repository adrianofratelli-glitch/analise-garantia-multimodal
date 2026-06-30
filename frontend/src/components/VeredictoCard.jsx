import Badge from '@leafygreen-ui/badge';

const ROTULO = {
  defeito_fabrica: { txt: 'Defeito de fábrica', variant: 'red' },
  defeito_transporte: { txt: 'Defeito de transporte', variant: 'yellow' },
  mau_uso: { txt: 'Mau uso', variant: 'lightgray' },
  inconclusivo: { txt: 'Inconclusivo', variant: 'blue' },
};

/** Card de veredito: classificação + barra de confiança + aviso de revisão humana. */
export default function VeredictoCard({ veredito }) {
  if (!veredito) return null;
  const r = ROTULO[veredito.classificacao] || { txt: veredito.classificacao, variant: 'darkgray' };
  const pct = Math.round((veredito.confianca ?? 0) * 100);

  return (
    <div className="card neutral">
      <div className="card-header">
        <span className="card-title">Veredito da triagem (IA)</span>
        <Badge variant={r.variant}>{r.txt}</Badge>
      </div>

      <div className="conf-row">
        <span className="conf-label">confiança</span>
        <div className="conf-track">
          <div className="conf-fill" style={{ width: `${pct}%` }} />
        </div>
        <span className="conf-pct mono">{pct}%</span>
      </div>

      <p style={{ marginTop: 12, color: 'var(--text-sec)' }}>{veredito.racional}</p>

      {veredito.sinais_observados?.length > 0 && (
        <div className="row" style={{ marginTop: 10 }}>
          {veredito.sinais_observados.map((s, i) => (
            <Badge key={i} variant="darkgray">{s}</Badge>
          ))}
        </div>
      )}

      <div className="aviso-humano">
        ⚠ Sujeito a revisão humana — não é decisão final (risco CDC).
      </div>

      {veredito._meta && (
        <div className="dim mono" style={{ marginTop: 8, fontSize: 11 }}>
          {veredito._meta.model} · {veredito._meta.latency_ms}ms ·
          {' '}{veredito._meta.input_tokens}+{veredito._meta.output_tokens} tokens ·
          {' '}{veredito._meta.precedentes_usados} precedentes
        </div>
      )}
    </div>
  );
}
