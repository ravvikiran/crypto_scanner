#!/usr/bin/env python3
"""
Start the Crypto Scanner Web UI.
This starts the Flask API server only.
"""

import os
import sys
from pathlib import Path

# Change to project directory
project_root = Path(__file__).parent
os.chdir(project_root)
sys.path.insert(0, str(project_root))

# Set default port
port = int(os.environ.get('PORT', 5002))

# Now import and run
from infrastructure.api import init_api, app
from collectors.crypto_data_fetcher import CryptoDataFetcher
from infrastructure.market_scheduler import MarketScheduler as CryptoScheduler
from storage import PerformanceTracker

# Initialize API with required components
print("Initializing API components...")
data_fetcher = CryptoDataFetcher()
market_scheduler = CryptoScheduler()
performance_tracker = PerformanceTracker()

# Create a minimal TradeJournal for API (using learning module)
from learning.trade_journal import TradeJournal as LearningTradeJournal
trade_journal = LearningTradeJournal(config=None)  # Will use default config

init_api(
    trade_journal_inst=trade_journal,
    data_fetcher_inst=data_fetcher,
    market_scheduler_inst=market_scheduler,
    performance_tracker_inst=performance_tracker,
    history_manager_inst=None
)

# Verify globals are set
from infrastructure import api as api_module
print(f"  trade_journal: {type(api_module.trade_journal)}")
print(f"  data_fetcher: {type(api_module.data_fetcher)}")
print("✓ API initialized")

# Start Flask
print(f"\n🚀 Starting Web UI on port {port}...")
print(f"   Dashboard: http://localhost:{port}")
print(f"   API: http://localhost:{port}/api/")
print("\nPress Ctrl+C to stop\n")

app.run(debug=False, host='0.0.0.0', port=port, threaded=True, use_reloader=False)