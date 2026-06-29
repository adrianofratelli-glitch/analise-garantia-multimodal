#!/usr/bin/env bash
# Comando único da PoV: prepara o que falta e sobe a aplicação.
#
#   ./run.sh           sobe backend (:8000) + frontend (:5173)
#   ./run.sh --seed     idem, mas roda o seed antes (popula a collection)
#
# É idempotente: cria o venv / instala as deps só na primeira vez; nas próximas
# execuções pula direto pra subir os servidores.
set -e
cd "$(dirname "$0")"

# 0. .env precisa existir e estar preenchido
if [ ! -f .env ]; then
  cp .env.example .env
  echo "✖ Criei .env a partir do .env.example."
  echo "  Preencha as credenciais (MONGODB_URI, ANTHROPIC_API_KEY, VOYAGE_API_KEY, S3_*) e rode de novo."
  exit 1
fi

# 1. backend — venv + deps (só na 1ª vez)
if [ ! -d backend/.venv ]; then
  echo "▶ criando venv e instalando deps do backend (1ª vez)…"
  python -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements.txt
else
  echo "✔ backend já preparado"
fi

# 2. frontend — node_modules (só na 1ª vez)
if [ ! -d frontend/node_modules ]; then
  echo "▶ instalando deps do frontend (1ª vez)…"
  (cd frontend && npm install)
else
  echo "✔ frontend já preparado"
fi

# 3. seed (opcional) — popula a collection e imprime o JSON do índice de vetor.
#    Rode na 1ª vez (ou quando quiser repopular). Depois o índice fica no Atlas.
if [ "$1" = "--seed" ]; then
  echo "▶ seed — populando POC.chamados…"
  (cd backend && ../backend/.venv/bin/python seed.py --reset cadeira)
  echo "  ↑ crie o índice 'chamados_vector' no Atlas com o JSON acima (só na 1ª vez)."
fi

# 4. backend FastAPI :8000 — só sobe se a porta estiver livre (preserva outras POCs)
if ! lsof -ti :8000 >/dev/null 2>&1; then
  echo "▶ backend FastAPI :8000"
  (cd backend && .venv/bin/uvicorn main:app --port 8000 &)
  sleep 2
else
  echo "✔ backend já rodando na :8000"
fi

# 5. frontend Vite :5173 (foreground — Ctrl+C encerra)
echo "▶ frontend Vite :5173 — abra a porta 5173 quando subir"
cd frontend && exec npx vite --port "${PORT:-5173}"
