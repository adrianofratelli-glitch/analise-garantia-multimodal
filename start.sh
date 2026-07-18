#!/usr/bin/env bash
# Boots the whole app: FastAPI (8100) in the background + Vite (5190) in the foreground.
set -e
cd "$(dirname "$0")"

# backend — only start it if port 8100 is free
if ! lsof -ti :8100 >/dev/null 2>&1; then
  echo "▶ backend FastAPI :8100"
  # --workers 1 explícito: métricas em processo e o change stream SSE assumem
  # processo único; múltiplos workers dividiriam contadores e duplicariam streams.
  (cd backend && .venv/bin/uvicorn main:app --port 8100 --workers 1 &)
  sleep 2
else
  echo "✔ backend already running on :8100"
fi

echo "▶ frontend Vite :5190"
cd frontend
# instala deps na primeira vez (LeafyGreen tem conflito de peer dep -> legacy-peer-deps)
[ -x node_modules/.bin/vite ] || npm install --legacy-peer-deps
# usa o binário local (npm run dev), não `npx vite` (que pega o vite global errado)
exec npm run dev -- --port "${PORT:-5190}"
