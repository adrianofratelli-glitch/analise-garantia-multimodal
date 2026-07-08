import Badge from '@leafygreen-ui/badge';
import Banner from '@leafygreen-ui/banner';

/** Verificação de identidade: a foto do cliente bate com as fotos de referência
 * do SKU (catalogo_fotos, $vectorSearch)? Sinal de produto certo/errado — não
 * de defeito, que continua sendo decisão do Claude via VeredictoCard. */
export default function IdentidadeCard({ identidade }) {
  if (!identidade) return null;
  const { score, fotos_comparadas, abaixo_threshold } = identidade;

  if (score === null) {
    return (
      <div className="card neutral">
        <div className="card-header">
          <span className="card-title">Verificação de identidade do produto</span>
          <Badge variant="lightgray">sem fotos de referência</Badge>
        </div>
        <p className="dim" style={{ marginTop: 8 }}>
          Este SKU ainda não tem fotos de catálogo seedadas em catalogo_fotos — etapa pulada.
        </p>
      </div>
    );
  }

  const pct = Math.round(score * 100);

  return (
    <div className="card neutral">
      <div className="card-header">
        <span className="card-title">Verificação de identidade do produto</span>
        <Badge variant={abaixo_threshold ? 'red' : 'green'}>{pct}% de similaridade</Badge>
      </div>
      <p className="dim" style={{ marginTop: 8 }}>
        Comparado ($vectorSearch) com {fotos_comparadas} foto(s) de referência do SKU no catálogo —
        embedding multimodal Voyage AI mede semelhança semântica com o produto, não detecta o defeito em si.
      </p>
      {abaixo_threshold && (
        <Banner variant="warning" darkMode style={{ marginTop: 10 }}>
          Similaridade baixa — a foto enviada pode não ser do produto comprado. Confirmar manualmente antes de aprovar.
        </Banner>
      )}
    </div>
  );
}
