#!/bin/bash
echo ""
echo " ============================================"
echo "  HXL Ontology Tagger - Starting..."
echo " ============================================"
echo ""

if ! command -v python3 &>/dev/null; then
    echo " ERROR: Python 3 not found."
    echo " Install from https://python.org"
    exit 1
fi

if [ ! -f ".deps_ok" ]; then
    echo " Installing packages (first run only, ~30 seconds)..."
    pip3 install -r requirements.txt --quiet
    touch .deps_ok
    echo " Done."
    echo ""
fi

if [ ! -f ".env" ]; then
    echo " NOTE: No .env file. Copy .env.example to .env and add your API key,"
    echo " or use the Settings button inside the app."
    echo ""
fi

echo " Starting at http://localhost:8000"
echo " Press Ctrl+C to stop."
echo ""

(sleep 2 && open "http://localhost:8000" 2>/dev/null || xdg-open "http://localhost:8000" 2>/dev/null) &
python3 app.py
