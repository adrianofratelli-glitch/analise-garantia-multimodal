#!/usr/bin/env bash
# Sobe a aplicação "MM — Análise de Garantia" e abre no navegador.
# Atalho: digite `image` no terminal (alias no ~/.zshrc).
set -e
ROOT="/Users/adriano.fratelli/Documents/MadeiraMadeira/mm-analise-garantia"
cd "$ROOT"

# --- backend (FastAPI :8100) ---
if lsof -ti :8100 >/dev/null 2>&1; then
  echo "✔ backend já rodando em :8100"
else
  echo "▶ subindo backend :8100"
  ( cd backend && nohup ./.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8100 \
      > /tmp/mm-garantia-backend.log 2>&1 & )
fi

# --- deps do frontend (primeira vez; LeafyGreen exige --legacy-peer-deps) ---
if [ ! -x frontend/node_modules/.bin/vite ]; then
  echo "▶ instalando dependências do frontend (primeira vez)..."
  ( cd frontend && npm install --legacy-peer-deps )
fi

# --- frontend (Vite :5190) ---
if lsof -ti :5190 >/dev/null 2>&1; then
  echo "✔ frontend já rodando em :5190"
else
  echo "▶ subindo frontend :5190"
  ( cd frontend && nohup ./node_modules/.bin/vite --port 5190 --host 127.0.0.1 \
      > /tmp/mm-garantia-frontend.log 2>&1 & )
fi

# --- espera ficar pronto e abre o navegador ---
printf "aguardando subir"
for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:5190 >/dev/null 2>&1 \
     && curl -fsS http://127.0.0.1:8100/api/health >/dev/null 2>&1; then
    echo ""
    echo "✓ pronto: http://localhost:5190"
    open http://localhost:5190
    echo "  logs:  /tmp/mm-garantia-backend.log  ·  /tmp/mm-garantia-frontend.log"
    echo "  parar: image-stop"
    exit 0
  fi
  printf "."
  sleep 1
done
echo ""
echo "⚠ não respondeu a tempo — veja os logs em /tmp/mm-garantia-*.log"
exit 1
