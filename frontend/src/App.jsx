import { useEffect, useState } from 'react';
import Portal from './tabs/Portal.jsx';
import Revisao from './tabs/Revisao.jsx';
import { api } from './api.js';

const TABS = ['01 · Portal de Garantia', '02 · Revisão Humana'];

export default function App() {
  const [selected, setSelected] = useState(0);

  // estado elevado: trocar de aba não apaga o resultado da análise nem a revisão.
  const [portalState, setPortalState] = useState({ resultado: null, step: 0 });
  const [revisaoState, setRevisaoState] = useState({ pendentes: [], selecionado: null });

  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(false);

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

  const panes = [
    <Portal state={portalState} setState={setPortalState} goRevisar={() => setSelected(1)} />,
    <Revisao state={revisaoState} setState={setRevisaoState} />,
  ];

  const counts = health?.counts ?? {};

  return (
    <>
      <nav className="top-nav">
        <div className="nav-inner">
          <span className="nav-logo">
            <span className="leaf">●</span> MM · Análise de Garantia
          </span>
          <div className="nav-pills">
            {TABS.map((name, i) => (
              <button
                key={name}
                className={`nav-pill ${i === selected ? 'active' : ''}`}
                onClick={() => setSelected(i)}
              >
                {name}
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
        <div className="hero-kicker">PoV · Triagem Multimodal de Garantia</div>
        <h1 className="page-title">
          Defeito vira <span>precedente</span> recuperável
        </h1>
        <p className="page-subtitle">
          Foto + checklist + descrição entram numa busca vetorial multimodal sobre
          chamados já resolvidos. O Claude propõe um veredito — sempre sujeito a
          revisão humana. Cada confirmação realimenta a base (flywheel).
        </p>

        <div className="stat-bar">
          <div className="stat-item">
            <div className="stat-val accent">{counts.total ?? '—'}</div>
            <div className="stat-label">chamados</div>
          </div>
          <div className="stat-item">
            <div className="stat-val accent">{counts.resolvido ?? '—'}</div>
            <div className="stat-label">precedentes resolvidos</div>
          </div>
          <div className="stat-item">
            <div className="stat-val accent">{counts.em_analise ?? '—'}</div>
            <div className="stat-label">em análise</div>
          </div>
          <div className="stat-item">
            <div className="stat-val">1024</div>
            <div className="stat-label">dim · voyage-multimodal-3</div>
          </div>
          <div className="stat-item">
            <div className="stat-val" style={{ fontSize: '1rem', lineHeight: '1.9' }}>
              {health?.model ?? '—'}
            </div>
            <div className="stat-label">modelo de visão</div>
          </div>
        </div>

        {panes.map((pane, i) => (
          <div key={i} style={{ display: i === selected ? 'block' : 'none' }}>
            <div className={i === selected ? 'fade-in' : ''}>{pane}</div>
          </div>
        ))}
      </main>

      <footer className="app-footer">
        <p>MongoDB Atlas · POC.chamados — $vectorSearch + voyage-multimodal-3 (Caminho B)</p>
      </footer>
    </>
  );
}
