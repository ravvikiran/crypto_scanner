#!/bin/bash
# Crypto Scanner - Web UI Launcher
# This script starts the Flask API for the web dashboard.

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Crypto Scanner AI - Web UI Launcher              ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo ""

# Check virtual environment
if [ ! -d ".venv" ]; then
    echo -e "${RED}❌ Virtual environment not found!${NC}"
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

# Check Flask
if ! python -c "import flask" 2>/dev/null; then
    echo -e "${RED}❌ Flask not installed!${NC}"
    echo -e "${YELLOW}Installing Flask...${NC}"
    pip install flask flask-cors
fi

# Parse args
MODE=${1:-"ui"}
PORT=${2:-5002}

case $MODE in
    "ui")
        echo -e "${GREEN}✓ Starting Web UI${NC}"
        echo -e "${YELLOW}Dashboard: http://localhost:${PORT}${NC}"
        echo ""
        export PORT
        python3 start_ui.py
        ;;
    "scanner")
        echo -e "${GREEN}✓ Starting Scanner Only${NC}"
        python3 main.py --schedule
        ;;
    "both")
        echo -e "${GREEN}✓ Starting Scanner + Web UI${NC}"
        echo -e "${YELLOW}Dashboard: http://localhost:${PORT}${NC}"
        echo ""
        # TODO: run scanner in background and UI in foreground
        echo "Not yet implemented. Use separate terminals:"
        echo "  Terminal 1: ./run_ui.sh scanner"
        echo "  Terminal 2: ./run_ui.sh ui"
        exit 1
        ;;
    "help")
        echo "Usage: ./run_ui.sh [MODE] [PORT]"
        echo ""
        echo "Modes:"
        echo "  ui       - Run Web UI only (default)"
        echo "  scanner  - Run scanner only (terminal mode)"
        echo "  both     - Run both (requires separate terminals)"
        echo "  help     - Show this help"
        echo ""
        echo "Examples:"
        echo "  ./run_ui.sh                    # UI on port 5002"
        echo "  ./run_ui.sh ui 8000            # UI on port 8000"
        echo "  ./run_ui.sh scanner            # Run scanner"
        ;;
    *)
        echo -e "${RED}Unknown mode: $MODE${NC}"
        echo "Use './run_ui.sh help' for usage"
        exit 1
        ;;
esac