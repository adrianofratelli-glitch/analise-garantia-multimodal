// HTTP client. Backend errors arrive as {error: {kind, message}} (503) and
// become ApiError — the UI shows them in a yellow Banner, never a stack trace.

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
    throw new ApiError('rede', 'Backend não respondeu. O FastAPI está rodando na porta 8100?');
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = body.error || {};
    throw new ApiError(err.kind || 'erro', err.message || `Erro HTTP ${res.status}`);
  }
  return body;
}

async function upload(path, formData) {
  // multipart — sem Content-Type manual (o browser põe o boundary)
  let res;
  try {
    res = await fetch(path, { method: 'POST', body: formData });
  } catch {
    throw new ApiError('rede', 'Backend não respondeu. O FastAPI está rodando na porta 8100?');
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
  analisar: (formData) => upload('/api/analisar', formData),
  pendentes: () => request('/api/chamados/pendentes'),
  revisar: (numero_chamado, resolucao_final) =>
    request('/api/revisar', {
      method: 'POST',
      body: JSON.stringify({ numero_chamado, resolucao_final }),
    }),
};
