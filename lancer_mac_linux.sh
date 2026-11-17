#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 collect.py
printf 'Ouvrir http://localhost:8000 dans un navigateur\n'
python3 -m http.server 8000
