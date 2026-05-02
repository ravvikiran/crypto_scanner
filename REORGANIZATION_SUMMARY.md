# Project Reorganization Summary

## What Changed

The crypto scanner project has been reorganized to improve maintainability and clarity. The main changes:

### New Directory Structure

```
crypto_scanner/
├── crypto_scanner/            # Main package (if installed)
├── legacy/                    # Deprecated NSE/stock market code
│   ├── data_fetcher.py
│   ├── history_manager.py
│   └── performance_tracker.py
├── infrastructure/            # Core infrastructure
│   ├── api.py                 # Flask REST API (moved from src/api.py)
│   ├── market_scheduler.py    # 24/7 market scheduler
│   └── scanner_scheduler.py   # APScheduler-based scanner scheduler
├── collectors/                # Data collection
│   ├── __init__.py            # MarketDataCollector, BinanceCollector
│   └── crypto_data_fetcher.py # CryptoDataFetcher (moved from src/)
├── alerts/                    # Notification system
│   ├── __init__.py
│   ├── alert_manager.py
│   ├── signal_publisher.py
│   ├── telegram_bot.py
│   └── signal_memory.py       # Moved from src/signal_memory.py
├── engines/                   # Core trading engines
│   ├── __init__.py
│   ├── market_sentiment_engine.py
│   ├── trend_alert_engine.py
│   ├── coin_filter_engine.py
│   ├── confluence_engine.py
│   ├── position_sizer.py
│   ├── optimization_engine.py
│   ├── market_regime_engine.py
│   ├── risk_management_engine.py
│   └── trade_validator.py     # Moved from src/trade_validator.py
├── scorer/                    # Signal scoring
│   ├── __init__.py
│   └── enhanced.py            # SignalScorerEnhanced (from src/signal_scorer.py)
├── learning/                  # Learning & self-adaptation
│   ├── __init__.py
│   ├── signal_tracker.py
│   ├── accuracy_scorer.py
│   ├── resolution_checker.py
│   ├── learning_engine.py
│   ├── trade_journal.py
│   ├── self_adaptation.py
│   ├── notifier.py
│   ├── pattern_learning.py   # Moved from src/pattern_learning.py
│   └── strategy_optimizer.py # Moved from src/strategy_optimizer.py
├── config/                    # Configuration management
├── models/                    # Data models
├── strategies/               # Trading strategies
├── ai/                       # AI/LLM integration
├── reasoning/                # Hybrid reasoning
├── dashboard/                # Console dashboard
├── storage/                  # Performance storage
├── static/                   # Web UI static assets
├── templates/                # Flask HTML templates
├── data/                     # Runtime data (databases, JSON)
├── logs/                     # Application logs
├── docs/                     # Documentation
├── main.py                   # CLI entry point
├── scanner.py                # Main orchestrator
├── start_ui.py               # Web UI starter
├── run_api.py                # Simple API runner
├── config.yaml               # Configuration file
└── requirements.txt          # Dependencies
```

## Files Moved

| From | To | Reason |
|------|----|--------|
| `src/api.py` | `infrastructure/api.py` | API is infrastructure |
| `src/market_scheduler.py` | `infrastructure/market_scheduler.py` | Scheduler infrastructure |
| `src/scheduler/scanner_scheduler.py` | `infrastructure/scanner_scheduler.py` | Scheduler code |
| `src/crypto_data_fetcher.py` | `collectors/crypto_data_fetcher.py` | Data collection module |
| `src/signal_memory.py` | `alerts/signal_memory.py` | Used by alert system |
| `src/signal_scorer.py` | `scorer/enhanced.py` | Enhanced scoring module |
| `src/trade_validator.py` | `engines/trade_validator.py` | Engine validation |
| `src/pattern_learning.py` | `learning/pattern_learning.py` | Learning component |
| `src/strategy_optimizer.py` | `learning/strategy_optimizer.py` | Learning component |
| `src/data_fetcher.py` | `legacy/` | Deprecated NSE code |
| `src/history_manager.py` | `legacy/` | Deprecated NSE code |
| `src/performance_tracker.py` | `legacy/` | Deprecated NSE code |
| `src/signal_tracker.py` | `legacy/` | Deprecated NSE version (different from learning.signal_tracker) |

## Import Changes

All imports updated to use new locations. Old `from src.xxx` imports replaced with:

- `from infrastructure.api import ...`
- `from collectors.xxx import ...`
- `from alerts.signal_memory import SignalMemory`
- `from scorer.enhanced import SignalScorerEnhanced`
- `from engines.trade_validator import TradeValidator`
- `from learning.pattern_learning import PatternLearning`
- `from learning.strategy_optimizer import StrategyOptimizer`
- `from infrastructure.scanner_scheduler import ScannerScheduler`
- `from infrastructure.market_scheduler import MarketScheduler`

No `src/` imports remain in any Python code.

## What Was Removed

- The `src/` directory as a package has been removed entirely.
- Legacy NSE-specific code moved to `legacy/` (kept for reference).
- Unused duplicate modules eliminated.

## Why This Organization?

- **Clear separation**: Core domain logic in top-level packages (config, models, collectors, etc.)
- **Infrastructure separated**: API and scheduling in `infrastructure/`
- **Active vs legacy**: Legacy NSE code isolated in `legacy/` (no longer cluttering active codebase)
- **Logical grouping**: Moved modules to packages where they logically belong (e.g., signal_memory → alerts)
- **Simpler imports**: All imports are now absolute from package root, no more `sys.path` hacks needed

## Impact on Running the Application

Entry points (`main.py`, `start_ui.py`, `run_api.py`) all work unchanged from the user's perspective. All CLI commands and API endpoints continue to function.

## Next Steps

- Update any remaining documentation referencing `src/` paths (see `PROJECT_STRUCTURE.md`)
- Consider removing the `legacy/` folder after confirming no references remain
- Optionally add `infrastructure/` and other new packages to git

## Final Structure (Current)

```
crypto_scanner/
├── main.py                   # CLI entry point
├── scanner.py                # Main orchestrator
├── start_ui.py               # Web UI entry point
├── run_api.py                # API runner
├── config.yaml               # Configuration file
├── requirements.txt          # Dependencies
│
├── ai/                       # AI/LLM integration
│   ├── __init__.py
│   ├── signal_validation_agent.py
│   ├── market_sentiment_analyzer.py
│   └── abstract.py
│
├── alerts/                   # Notification system
│   ├── __init__.py
│   ├── alert_manager.py
│   ├── signal_publisher.py
│   ├── signal_memory.py
│   └── telegram_bot.py
│
├── collectors/               # Data collection
│   ├── __init__.py
│   └── crypto_data_fetcher.py
│
├── config/                   # Configuration management
│   └── __init__.py
│
├── dashboard/                # Console dashboard
│   └── __init__.py
│
├── data/                     # Runtime data
│   └── learning_history.json
│
├── docs/                     # Documentation
│   ├── README.md
│   ├── archive/              # Archived old docs
│   └── (other docs)
│
├── engines/                  # Core trading engines
│   ├── __init__.py
│   ├── market_regime_engine.py
│   ├── market_sentiment_engine.py
│   ├── trend_alert_engine.py
│   ├── coin_filter_engine.py
│   ├── confluence_engine.py
│   ├── position_sizer.py
│   ├── optimization_engine.py
│   ├── risk_management_engine.py
│   └── trade_validator.py
│
├── filters/                  # Signal filters
│   └── __init__.py           # BitcoinFilter
│
├── indicators/               # Technical indicators
│   └── __init__.py           # IndicatorEngine
│
├── infrastructure/           # Core infrastructure
│   ├── __init__.py
│   ├── api.py                # Flask REST API
│   ├── scanner_scheduler.py
│   └── market_scheduler.py
│
├── learning/                 # Learning system
│   ├── __init__.py
│   ├── signal_tracker.py
│   ├── accuracy_scorer.py
│   ├── resolution_checker.py
│   ├── learning_engine.py
│   ├── trade_journal.py
│   ├── self_adaptation.py
│   ├── notifier.py
│   ├── pattern_learning.py
│   └── strategy_optimizer.py
│
├── legacy/                   # Deprecated NSE code
│   ├── data_fetcher.py
│   ├── history_manager.py
│   └── performance_tracker.py
│
├── logs/                     # Application logs
│
├── memory/                   # Memory module (placeholder)
│   └── __init__.py
│
├── models/                   # Data models
│   └── __init__.py
│
├── reasoning/                # Hybrid reasoning
│   └── __init__.py
│
├── scorer/                   # Signal scoring
│   ├── __init__.py
│   └── enhanced.py
│
├── static/                   # Web UI assets
│   ├── css/
│   └── js/
│
├── storage/                  # Data persistence
│   └── __init__.py
│
├── strategies/               # Trading strategies
│   ├── __init__.py
│   ├── mtf_engine.py
│   └── prd_signal_engine.py
│
├── templates/                # HTML templates
└── tests/                    # Test suite (to be populated)
```
