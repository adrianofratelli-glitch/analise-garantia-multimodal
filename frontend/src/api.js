// Cliente HTTP. Erros do backend chegam como {error: {kind, message}} (503/404)
// e viram ApiError — a UI mostra num Banner amarelo, nunca um stack trace.

export class ApiError extends Error {
  constructor(kind, message) {
    super(message);
    this.kind = kind;
  }
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
  } catch {
    throw new ApiError('rede', 'Backend não respondeu. O FastAPI está rodando na porta 8000?');
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = body.error || {};
    throw new ApiError(err.kind || 'erro', err.message || `Erro HTTP ${res.status}`);
  }
  return body;
}

export const api = {
  health: () => request('/api/health'),

  pedidos: () => request('/api/pedidos'),

  lookup: (numero_pedido) =>
    request('/api/lookup', { method: 'POST', body: JSON.stringify({ numero_pedido }) }),

  checklist: (categoria) => request(`/api/checklist/${categoria}`),

  // multipart — NÃO setar Content-Type (o browser põe o boundary)
  analisar: async ({ imagem, numero_pedido, sku, checklist, descricao }) => {
    const fd = new FormData();
    fd.append('imagem', imagem);
    fd.append('numero_pedido', numero_pedido);
    fd.append('sku', sku);
    fd.append('descricao', descricao || '');
    (checklist || []).forEach((id) => fd.append('checklist', id));

    let res;
    try {
      res = await fetch('/api/analisar', { method: 'POST', body: fd });
    } catch {
      throw new ApiError('rede', 'Backend não respondeu. O FastAPI está rodando na porta 8000?');
    }
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = body.error || {};
      throw new ApiError(err.kind || 'erro', err.message || `Erro HTTP ${res.status}`);
    }
    return body;
  },

  revisar: (numero_chamado, resolucao_final) =>
    request('/api/revisar', {
      method: 'POST',
      body: JSON.stringify({ numero_chamado, resolucao_final }),
    }),
};
