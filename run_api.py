#!/usr/bin/env python3
"""
Simple script to run just the Flask API for the Crypto Scanner UI.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Ensure learning module is importable
learning_path = project_root / 'learning'
if learning_path.exists():
    sys.path.insert(0, str(learning_path.parent))

# Set environment
port = int(os.environ.get('PORT', '5002'))

# Import and run
from infrastructure.api import app

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Crypto Scanner Web API")
    print("=" * 60)
    print(f"Dashboard: http://localhost:{port}")
    print("API Endpoints:")
    print("  GET  /api/dashboard")
    print("  GET  /api/trades/open")
    print("  GET  /api/trades/history")
    print("  GET  /api/performance/summary")
    print("  GET  /api/signals/top5")
    print("  GET  /api/analysis/market-sentiment")
    print("  GET  /api/scanner/status")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=port, use_reloader=False)