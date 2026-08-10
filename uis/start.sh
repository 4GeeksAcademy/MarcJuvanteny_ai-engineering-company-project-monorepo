#!/bin/sh
set -eu

cd /app/website
npm run dev -- --hostname 0.0.0.0 --port 3000 &
WEBSITE_PID=$!

cd /app/backoffice
npm run dev -- --hostname 0.0.0.0 --port 3001 &
BACKOFFICE_PID=$!

trap 'kill "$WEBSITE_PID" "$BACKOFFICE_PID"' INT TERM

wait "$WEBSITE_PID" "$BACKOFFICE_PID"
