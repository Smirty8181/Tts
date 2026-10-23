#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/frontend"
if [ ! -d node_modules ]; then
  echo "Installing frontend dependencies..."
  npm install
fi
echo "Starting STREAM SENTINEL at http://localhost:5173"
npm run dev
