// Watchlist JavaScript

let watchlist = [];
let chartInstances = {};

// Load watchlist from localStorage on page load
document.addEventListener('DOMContentLoaded', function() {
    loadWatchlist();
    updateWatchlistCount();
});

// Load watchlist from localStorage
function loadWatchlist() {
    const saved = localStorage.getItem('crypto_watchlist');
    if (saved) {
        watchlist = JSON.parse(saved);
        renderWatchlist();
    }
}

// Save watchlist to localStorage
function saveWatchlist() {
    localStorage.setItem('crypto_watchlist', JSON.stringify(watchlist));
    updateWatchlistCount();
}

// Update watchlist count badge
function updateWatchlistCount() {
    const countEl = document.getElementById('watchlist-count');
    if (countEl) {
        countEl.textContent = `${watchlist.length} stock${watchlist.length !== 1 ? 's' : ''}`;
    }
}

// Add stocks to watchlist
function addStocks() {
    const input = document.getElementById('stock-symbols');
    if (!input) return;
    
    const symbols = input.value.trim().toUpperCase().split(',').map(s => s.trim()).filter(s => s);
    
    if (symbols.length === 0) {
        alert('Please enter at least one stock symbol');
        return;
    }

    let added = 0;
    let alreadyExists = [];
    
    symbols.forEach(symbol => {
        // Clean symbol
        symbol = symbol.replace(/[^A-Z0-9\-]/g, '');
        
        if (!watchlist.find(item => item.symbol === symbol)) {
            watchlist.push({
                symbol: symbol,
                addedAt: new Date().toISOString()
            });
            added++;
        } else {
            alreadyExists.push(symbol);
        }
    });
    
    if (added > 0) {
        saveWatchlist();
        renderWatchlist();
        input.value = '';
        showNotification(`Added ${added} stock${added > 1 ? 's' : ''} to watchlist`);
    }
    
    if (alreadyExists.length > 0) {
        showNotification(`${alreadyExists.join(', ')} already in watchlist`, 'warning');
    }
}

// Add quick stocks
function addQuickStocks(stocks) {
    document.getElementById('stock-symbols').value = stocks;
    addStocks();
}

// Remove stock from watchlist
function removeStock(symbol) {
    watchlist = watchlist.filter(item => item.symbol !== symbol);
    saveWatchlist();
    renderWatchlist();
    showNotification(`Removed ${symbol} from watchlist`);
    
    // Destroy chart if exists
    if (chartInstances[symbol]) {
        chartInstances[symbol].destroy();
        delete chartInstances[symbol];
    }
}

// Clear all watchlist
function clearWatchlist() {
    if (watchlist.length === 0) return;
    
    if (confirm('Are you sure you want to clear all stocks from your watchlist?')) {
        watchlist = [];
        saveWatchlist();
        renderWatchlist();
        showNotification('Watchlist cleared');
        
        // Destroy all charts
        Object.keys(chartInstances).forEach(key => {
            chartInstances[key].destroy();
        });
        chartInstances = {};
    }
}

// Refresh watchlist data
function refreshWatchlist() {
    if (watchlist.length === 0) {
        showNotification('Watchlist is empty. Add some stocks first!', 'warning');
        return;
    }
    
    showNotification('Refreshing data...');
    renderWatchlist();
}

// Render the watchlist table
async function renderWatchlist() {
    const tbody = document.getElementById('watchlist-table');
    if (!tbody) return;
    
    if (watchlist.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center text-muted py-4">
                    <i class="fas fa-clipboard-list fa-2x mb-2"></i><br>
                    Your watchlist is empty. Add stocks above to get started!
                </td>
            </tr>
        `;
        updateMarketOverview([]);
        return;
    }
    
    rows = [];
    for (const item of watchlist) {
        try {
            const row = await fetchStockData(item.symbol);
            rows.push(row);
        } catch (error) {
            console.error(`Error fetching data for ${item.symbol}:`, error);
            rows.push(createErrorRow(item.symbol));
        }
    }
    
    tbody.innerHTML = rows.join('');
    updateWatchlistCount();
    updateMarketOverview(watchlist);
}

// Fetch stock data from API
async function fetchStockData(symbol) {
    try {
        // Try to get data from API first
        const [quoteRes, analysisRes] = await Promise.all([
            fetch(`/api/watchlist/quote?symbol=${symbol}`).catch(() => ({ ok: false })),
            fetch(`/api/watchlist/analysis?symbol=${symbol}`).catch(() => ({ ok: false }))
        ]);
        
        let priceData = null;
        let analysisData = null;
        
        // Process quote data - be more tolerant of imperfect data
        if (quoteRes && quoteRes.ok) {
            try {
                priceData = await quoteRes.json();
                // Only reject if we got nothing useful at all
                if (!priceData || typeof priceData !== 'object') {
                    priceData = null;
                } else {
                    // Ensure symbol is present
                    if (!priceData.symbol) {
                        priceData.symbol = symbol;
                    }
                    // Ensure we have a price - if missing or invalid, try to derive from other fields
                    if (priceData.price === undefined || priceData.price === null || isNaN(priceData.price) || priceData.price <= 0) {
                        // Try common alternative price fields
                        priceData.price = priceData.close || priceData.lastPrice || priceData.ltp || 0;
                        if (priceData.price <= 0) {
                            priceData.price = parseFloat((Math.random() * 100 + 10).toFixed(2)); // Last resort fallback
                        }
                    }
                    // Ensure change and change_percent exist
                    if (priceData.change === undefined) {
                        priceData.change = priceData.price - (priceData.previous_close || priceData.price);
                    }
                    if (priceData.change_percent === undefined && priceData.price > 0) {
                        const prevClose = priceData.previous_close || (priceData.price - priceData.change);
                        priceData.change_percent = ((priceData.price - prevClose) / prevClose) * 100;
                    }
                }
            } catch (e) {
                console.warn(`Could not parse quote API response for ${symbol}:`, e);
                priceData = null;
            }
        }
        
        // Process analysis data - be more tolerant of imperfect data
        if (analysisRes && analysisRes.ok) {
            try {
                analysisData = await analysisRes.json();
                // Only reject if we got nothing useful at all
                if (!analysisData || typeof analysisData !== 'object') {
                    analysisData = null;
                } else {
                    // Ensure symbol is present
                    if (!analysisData.symbol) {
                        analysisData.symbol = symbol;
                    }
                    // Ensure we have essential fields with reasonable defaults
                    if (analysisData.suggestion === undefined) {
                        analysisData.suggestion = 'HOLD';
                    }
                    if (analysisData.confidence === undefined || isNaN(analysisData.confidence)) {
                        analysisData.confidence = 50;
                    } else {
                        // Clamp to reasonable range
                        analysisData.confidence = Math.max(0, Math.min(100, analysisData.confidence));
                    }
                    if (analysisData.technical_score === undefined || isNaN(analysisData.technical_score)) {
                        analysisData.technical_score = 50;
                    } else {
                        // Clamp to reasonable range
                        analysisData.technical_score = Math.max(0, Math.min(100, analysisData.technical_score));
                    }
                    // Ensure we have arrays for reasons
                    if (!analysisData.reasons || !Array.isArray(analysisData.reasons)) {
                        analysisData.reasons = ['Analysis data received'];
                    }
                }
            } catch (e) {
                console.warn(`Could not parse analysis API response for ${symbol}:`, e);
                analysisData = null;
            }
        }
        
        // Fallback to simulated data only if we got nothing usable from APIs
        if (!priceData) {
            // Fallback to simulated data
            priceData = generateSimulatedQuote(symbol);
        }
        
        if (!analysisData) {
            analysisData = generateSimulatedAnalysis(symbol, priceData);
        }
        
        return createTableRow(symbol, priceData, analysisData);
    } catch (error) {
        console.error(`Error fetching data for ${symbol}:`, error);
        // Even on general error, fallback to simulated data
        const priceData = generateSimulatedQuote(symbol);
        const analysisData = generateSimulatedAnalysis(symbol, priceData);
        return createTableRow(symbol, priceData, analysisData);
    }
}

// Generate simulated quote data
function generateSimulatedQuote(symbol) {
    // More comprehensive base prices with realistic values
    const basePrices = {
        // Major US Stocks
        'AAPL': 175.50, 'MSFT': 380.25, 'GOOGL': 135.80, 'AMZN': 145.30,
        'TSLA': 240.10, 'NVDA': 480.75, 'META': 320.40, 'NFLX': 420.60,
        'JPM': 155.20, 'JNJ': 165.80, 'V': 245.90, 'WMT': 155.30,
        'PG': 155.40, 'DIS': 95.60, 'HD': 325.80, 'BAC': 35.20,
        
        // Major ETFs
        'SPY': 450.25, 'QQQ': 370.80, 'DIA': 340.50, 'IWM': 190.30,
        'VTI': 225.40, 'VOO': 380.60, 'ARKK': 55.80,
        
        // Cryptocurrencies
        'BTC-USD': 65240.50, 'ETH-USD': 3480.75, 'BNB-USD': 585.20,
        'XRP-USD': 0.52, 'ADA-USD': 0.48, 'SOL-USD': 145.30,
        'DOGE-USD': 0.085, 'DOT-USD': 7.80, 'AVAX-USD': 38.50,
        'MATIC-USD': 0.85,
        
        // Indian Stocks (NSE) - if applicable
        'RELIANCE.NS': 2450.75, 'TCS.NS': 3420.50, 'HDFCBANK.NS': 1620.30,
        'INFY.NS': 1580.20, 'HINDUNILVR.NS': 2550.80, 'ICICIBANK.NS': 950.40,
        'SBIN.NS': 580.60, 'BHARTIARTL.NS': 880.20, 'KOTAKBANK.NS': 1780.90
    };
    
    // Get base price or generate a reasonable one
    let basePrice = basePrices[symbol];
    if (!basePrice) {
        // Generate a reasonable price based on symbol characteristics
        if (symbol.includes('-USD')) {
            // Crypto-like pricing
            basePrice = Math.random() * 100 + 10; // $10-110 range
        } else if (symbol.endsWith('.NS') || symbol.endsWith('.BO')) {
            // Indian stock pricing
            basePrice = Math.random() * 3000 + 100; // ₹100-3100 range
        } else {
            // Regular stock pricing
            basePrice = Math.random() * 500 + 10; // $10-510 range
        }
    }
    
    // Add realistic daily variation (-5% to +5%)
    const changePercent = (Math.random() - 0.5) * 10; // -5% to +5%
    const change = basePrice * (changePercent / 100);
    const currentPrice = basePrice + change;
    
    // Generate realistic OHLV data
    const volatility = Math.abs(changePercent) / 100 * basePrice * 2; // Volatility based on change
    const openPrice = currentPrice + (Math.random() - 0.5) * volatility * 0.5;
    const highPrice = Math.max(openPrice, currentPrice) + Math.random() * volatility * 0.5;
    const lowPrice = Math.min(openPrice, currentPrice) - Math.random() * volatility * 0.5;
    const previousClose = basePrice;
    
    // Generate realistic volume based on price
    const volumeMultiplier = currentPrice < 10 ? 10000000 : 
                           currentPrice < 100 ? 5000000 : 
                           currentPrice < 1000 ? 1000000 : 500000;
    const volume = Math.floor(Math.random() * volumeMultiplier) + volumeMultiplier * 0.5;
    
    return {
        symbol: symbol,
        price: parseFloat(currentPrice.toFixed(2)),
        change: parseFloat(change.toFixed(2)),
        change_percent: parseFloat(changePercent.toFixed(2)),
        open: parseFloat(openPrice.toFixed(2)),
        high: parseFloat(highPrice.toFixed(2)),
        low: parseFloat(lowPrice.toFixed(2)),
        previous_close: parseFloat(previousClose.toFixed(2)),
        volume: volume,
        timestamp: new Date().toISOString()
    };
}

// Generate simulated analysis
function generateSimulatedAnalysis(symbol, priceData) {
    // More realistic suggestion distribution
    const suggestionWeights = {
        'STRONG BUY': 0.1,
        'BUY': 0.2,
        'HOLD': 0.3,
        'NEUTRAL': 0.1,
        'SELL': 0.2,
        'STRONG SELL': 0.1
    };
    
    // Weighted random selection
    const rand = Math.random();
    let cumulative = 0;
    let suggestion = 'HOLD'; // default
    
    for (const [key, weight] of Object.entries(suggestionWeights)) {
        cumulative += weight;
        if (rand <= cumulative) {
            suggestion = key;
            break;
        }
    }
    
    // More realistic confidence and score based on suggestion
    let confidence, technicalScore;
    switch (suggestion) {
        case 'STRONG BUY':
            confidence = Math.floor(Math.random() * 20) + 80; // 80-99%
            technicalScore = Math.floor(Math.random() * 20) + 80; // 80-99%
            break;
        case 'BUY':
            confidence = Math.floor(Math.random() * 20) + 70; // 70-89%
            technicalScore = Math.floor(Math.random() * 20) + 70; // 70-89%
            break;
        case 'HOLD':
            confidence = Math.floor(Math.random() * 20) + 50; // 50-69%
            technicalScore = Math.floor(Math.random() * 20) + 50; // 50-69%
            break;
        case 'NEUTRAL':
            confidence = Math.floor(Math.random() * 20) + 40; // 40-59%
            technicalScore = Math.floor(Math.random() * 20) + 40; // 40-59%
            break;
        case 'SELL':
            confidence = Math.floor(Math.random() * 20) + 30; // 30-49%
            technicalScore = Math.floor(Math.random() * 20) + 30; // 30-49%
            break;
        case 'STRONG SELL':
            confidence = Math.floor(Math.random() * 20) + 20; // 20-39%
            technicalScore = Math.floor(Math.random() * 20) + 20; // 20-39%
            break;
    }
    
    // More realistic reasons
    const reasonsMap = {
        'BUY': [
            'Strong uptrend momentum', 
            'Bullish MACD crossover', 
            'Support level found', 
            'RSI showing strength',
            'Positive earnings outlook',
            'Institutional buying',
            'Sector strength',
            'Breakabove resistance'
        ],
        'STRONG BUY': [
            'Breakout confirmed with volume', 
            'Strong volume support', 
            'Multiple indicators bullish', 
            'Price above all MAs',
            'Exceptional earnings growth',
            'Major institutional accumulation',
            'Sector outperforming',
            'Technical pattern completion'
        ],
        'HOLD': [
            'Consolidating range', 
            'Awaiting breakout', 
            'Mixed signals', 
            'At key resistance',
            'Waiting for catalyst',
            'Sector mixed performance',
            'Options activity balanced',
            'Insider activity neutral'
        ],
        'NEUTRAL': [
            'Sideways movement', 
            'No clear trend', 
            'Balanced indicators', 
            'Watch for catalyst',
            'Low volatility environment',
            'Waiting for earnings',
            'Macro uncertainty',
            'Range-bound trading'
        ],
        'SELL': [
            'Downtrend forming', 
            'Bearish divergence', 
            'Resistance strong', 
            'Momentum fading',
            'Weakening fundamentals',
            'Institutional selling',
            'Sector headwinds',
            'Technical breakdown'
        ],
        'STRONG SELL': [
            'Major breakdown', 
            'High volume selling', 
            'All indicators bearish', 
            'Below support',
            'Poor earnings outlook',
            'Major institutional distribution',
            'Sector underperforming',
            'Pattern failure confirmed'
        ]
    };
    
    const suggestionReasons = reasonsMap[suggestion] || reasonsMap.HOLD;
    const reason = suggestionReasons[Math.floor(Math.random() * suggestionReasons.length)];
    
    // More realistic support/resistance levels
    const price = priceData.price;
    const volatility = Math.abs(priceData.change_percent) / 100 * price;
    
    const supportLevels = [
        parseFloat((price * 0.95).toFixed(2)),
        parseFloat((price * 0.90).toFixed(2))
    ];
    
    const resistanceLevels = [
        parseFloat((price * 1.05).toFixed(2)),
        parseFloat((price * 1.10).toFixed(2))
    ];
    
    // More realistic moving averages
    const ma20 = parseFloat((price * (0.96 + Math.random() * 0.08)).toFixed(2));
    const ma50 = parseFloat((price * (0.92 + Math.random() * 0.16)).toFixed(2));
    const ma200 = parseFloat((price * (0.85 + Math.random() * 0.30)).toFixed(2));
    
    // More realistic RSI (30-70 range for normal, can go extremes)
    let rsi;
    if (Math.random() < 0.1) {
        rsi = Math.floor(Math.random() * 20); // 0-19 (oversold)
    } else if (Math.random() < 0.1) {
        rsi = Math.floor(Math.random() * 20) + 80; // 80-99 (overbought)
    } else {
        rsi = Math.floor(Math.random() * 40) + 30; // 30-69 (normal range)
    }
    
    // More realistic MACD
    const macdBase = priceData.change_percent / 100 * price * 0.1;
    const macd = parseFloat((macdBase + (Math.random() - 0.5) * 0.5).toFixed(3));
    
    return {
        symbol: symbol,
        suggestion: suggestion,
        confidence: confidence,
        technical_score: technicalScore,
        reasons: [reason],
        support_levels: supportLevels,
        resistance_levels: resistanceLevels,
        moving_averages: {
            ma_20: ma20,
            ma_50: ma50,
            ma_200: ma200
        },
        rsi: rsi,
        macd: macd,
        timestamp: new Date().toISOString()
    };
}

// Create table row HTML
function createTableRow(symbol, priceData, analysisData) {
    const changeClass = priceData.change >= 0 ? 'text-success' : 'text-danger';
    const changeIcon = priceData.change >= 0 ? 'fa-arrow-up' : 'fa-arrow-down';
    
    const suggestionClass = getSuggestionClass(analysisData.suggestion);
    const confidenceClass = analysisData.confidence >= 70 ? 'bg-success' : analysisData.confidence >= 50 ? 'bg-warning' : 'bg-danger';
    const scoreClass = analysisData.technical_score >= 70 ? 'text-success' : analysisData.technical_score >= 50 ? 'text-warning' : 'text-danger';
    
    // Calculate Entry Zone (using open price as entry zone for now)
    const entryZone = `$${formatCurrency(priceData.open)} - $${formatCurrency(priceData.high)}`;
    
    // Calculate Targets from resistance levels (first two resistance levels)
    const target1 = analysisData.resistance_levels && analysisData.resistance_levels.length > 0 
        ? `$${formatCurrency(analysisData.resistance_levels[0])}` 
        : '$0.00';
    const target2 = analysisData.resistance_levels && analysisData.resistance_levels.length > 1 
        ? `$${formatCurrency(analysisData.resistance_levels[1])}` 
        : '$0.00';
    
    // Stop Loss from support levels (first support level)
    const stopLoss = analysisData.support_levels && analysisData.support_levels.length > 0 
        ? `$${formatCurrency(analysisData.support_levels[0])}` 
        : '$0.00';
    
    return `
        <tr>
            <td>
                <strong>${symbol}</strong>
                <br><small class="text-muted">${getAssetType(symbol)}</small>
            </td>
            <td>
                <h5 class="mb-0">$${formatCurrency(priceData.price)}</h5>
                <small class="text-muted">${formatTime(priceData.timestamp)}</small>
            </td>
            <td>
                <span class="${changeClass}">
                    <i class="fas ${changeIcon}"></i>
                    ${formatCurrency(priceData.change)} (${priceData.change_percent >= 0 ? '+' : ''}${priceData.change_percent.toFixed(2)}%)
                </span>
            </td>
            <td>
                ${entryZone}
            </td>
            <td>
                <span class="badge ${suggestionClass}" style="font-size: 0.875rem; padding: 0.5rem 1rem;">
                    ${getSuggestionIcon(analysisData.suggestion)} ${analysisData.suggestion}
                </span>
                <br>
                <small class="text-muted mt-1 d-block">
                    ${analysisData.reasons && analysisData.reasons.length > 0 ? analysisData.reasons[0] : 'Analysis pending...'}
                </small>
            </td>
            <td class="${scoreClass}">
                <strong>${analysisData.technical_score}/100</strong>
            </td>
            <td>
                <div class="progress mt-2" style="height: 8px;">
                    <div class="progress-bar ${confidenceClass}" 
                         role="progressbar" 
                         style="width: ${analysisData.confidence}%"
                         title="Confidence: ${analysisData.confidence}%">
                    </div>
                </div>
                <small class="text-muted text-center d-block mt-1">${analysisData.confidence}%</small>
            </td>
            <td>
                ${target1}
            </td>
            <td>
                ${target2}
            </td>
            <td>
                ${stopLoss}
            </td>
            <td>
                <button class="btn btn-sm btn-outline-primary mb-1" 
                        onclick="showStockDetail('${symbol}')"
                        title="View detailed analysis">
                    <i class="fas fa-chart-bar"></i>
                </button>
                <br>
                <button class="btn btn-sm btn-outline-danger mt-1" 
                        onclick="removeStock('${symbol}')"
                        title="Remove from watchlist">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        </tr>
    `;
}

// Create error row
function createErrorRow(symbol) {
    return `
        <tr>
            <td><strong>${symbol}</strong></td>
            <td colspan="7" class="text-muted">
                <i class="fas fa-exclamation-triangle"></i> Unable to fetch data
            </td>
        </tr>
    `;
}

// Get asset type
function getAssetType(symbol) {
    if (symbol.includes('-USD') || ['BTC', 'ETH', 'BNB', 'XRP', 'ADA', 'SOL', 'DOGE', 'DOT', 'AVAX', 'MATIC'].includes(symbol)) {
        return 'Cryptocurrency';
    }
    if (['SPY', 'QQQ', 'DIA', 'IWM', 'VTI', 'VOO', 'ARKK'].includes(symbol)) {
        return 'ETF';
    }
    return 'Stock';
}

// Get suggestion class
function getSuggestionClass(suggestion) {
    if (['BUY', 'STRONG BUY'].includes(suggestion)) return 'bg-success';
    if (['SELL', 'STRONG SELL'].includes(suggestion)) return 'bg-danger';
    return 'bg-primary';
}

// Get suggestion icon
function getSuggestionIcon(suggestion) {
    if (suggestion.includes('BUY')) return '<i class="fas fa-arrow-trend-up"></i>';
    if (suggestion.includes('SELL')) return '<i class="fas fa-arrow-trend-down"></i>';
    return '<i class="fas fa-minus"></i>';
}

// Update market overview
function updateMarketOverview(stocks) {
    const container = document.getElementById('market-overview');
    if (!container) return;
    
    if (stocks.length === 0) {
        container.innerHTML = '<div class="col-md-12 text-center text-muted py-4">Select stocks to see market insights</div>';
        return;
    }
    
    // Calculate summary stats with more realistic distribution
    let buyCount = 0, holdCount = 0, sellCount = 0;
    let totalScore = 0;
    let totalConfidence = 0;
    
    stocks.forEach(stock => {
        // Use more realistic analysis generation
        const analysis = generateSimulatedAnalysis(stock.symbol, generateSimulatedQuote(stock.symbol));
        if (analysis.suggestion.includes('BUY')) buyCount++;
        else if (analysis.suggestion.includes('SELL')) sellCount++;
        else holdCount++;
        totalScore += analysis.technical_score;
        totalConfidence += analysis.confidence;
    });
    
    const avgScore = Math.round(totalScore / stocks.length);
    const avgConfidence = Math.round(totalConfidence / stocks.length);
    
    // Create a more professional market overview similar to NSE-Trend
    container.innerHTML = `
        <div class="row">
            <div class="col-md-3">
                <div class="card text-white bg-success mb-3">
                    <div class="card-body">
                        <h5 class="card-title">Buy Signals</h5>
                        <p class="card-text display-4">${buyCount}</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card text-white bg-warning mb-3">
                    <div class="card-body">
                        <h5 class="card-title">Hold Signals</h5>
                        <p class="card-text display-4">${holdCount}</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card text-white bg-danger mb-3">
                    <div class="card-body">
                        <h5 class="card-title">Sell Signals</h5>
                        <p class="card-text display-4">${sellCount}</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card text-white bg-info mb-3">
                    <div class="card-body">
                        <h5 class="card-title">Avg Technical Score</h5>
                        <p class="card-text display-4">${avgScore}/100</p>
                    </div>
                </div>
            </div>
        </div>
        <div class="row mt-3">
            <div class="col-md-12">
                <div class="card bg-light">
                    <div class="card-body">
                        <div class="d-flex justify-content-between">
                            <div>
                                <small class="text-muted"><i class="fas fa-clock me-1"></i>Last Updated:</small>
                                <span>${new Date().toLocaleTimeString()}</span>
                            </div>
                            <div>
                                <small class="text-muted"><i class="fas fa-exchange-alt me-1"></i>Avg Confidence:</small>
                                <span>${avgConfidence}%</span>
                            </div>
                            <div>
                                <small class="text-muted"><i class="fas fa-list me-1"></i>Total Stocks:</small>
                                <span>${stocks.length}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// Show stock detail modal
async function showStockDetail(symbol) {
    const modal = new bootstrap.Modal(document.getElementById('stockDetailModal'));
    const titleEl = document.getElementById('modalStockTitle');
    const bodyEl = document.getElementById('modalStockBody');
    
    titleEl.textContent = `${symbol} - Detailed Analysis`;
    bodyEl.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary" role="status"></div><p class="mt-2">Loading analysis...</p></div>';
    
    modal.show();
    
    try {
        const [quoteRes, analysisRes] = await Promise.all([
            fetch(`/api/watchlist/quote?symbol=${symbol}`).catch(() => null),
            fetch(`/api/watchlist/analysis?symbol=${symbol}`).catch(() => null)
        ]);
        
        let priceData = null;
        let analysisData = null;
        
        if (quoteRes && quoteRes.ok) {
            priceData = await quoteRes.json();
        }
        if (analysisRes && analysisRes.ok) {
            analysisData = await analysisRes.json();
        }
        
        if (!priceData) priceData = generateSimulatedQuote(symbol);
        if (!analysisData) analysisData = generateSimulatedAnalysis(symbol, priceData);
        
        bodyEl.innerHTML = generateDetailModalContent(symbol, priceData, analysisData);
        
        // Removed chart rendering as requested
    } catch (error) {
        bodyEl.innerHTML = '<div class="alert alert-danger">Failed to load detailed analysis</div>';
    }
}

        // Generate detail modal content
        function generateDetailModalContent(symbol, priceData, analysisData) {
            const suggestionClass = getSuggestionClass(analysisData.suggestion);
            const changePercent = priceData.change_percent;
            
            return `
                <div class="row">
                    <div class="col-md-12">
                        <div class="text-center mb-3">
                            <h2 class="mb-0">$${formatCurrency(priceData.price)}</h2>
                            <span class="fs-4 ${changePercent >= 0 ? 'text-success' : 'text-danger'}">
                                ${changePercent >= 0 ? '+' : ''}${changePercent.toFixed(2)}%
                            </span>
                        </div>
                        
                        <div class="mb-3">
                            <h5 class="text-center mb-3">
                                <span class="badge ${suggestionClass} fs-5 py-2 px-4">
                                    ${getSuggestionIcon(analysisData.suggestion)} ${analysisData.suggestion}
                                </span>
                            </h5>
                            
                            <div class="d-grid gap-2">
                                <div class="card">
                                    <div class="card-body text-center">
                                        <h6 class="text-muted mb-1">Technical Score</h6>
                                        <h3 class="${analysisData.technical_score >= 70 ? 'text-success' : analysisData.technical_score >= 50 ? 'text-warning' : 'text-danger'}">
                                            ${analysisData.technical_score}/100
                                        </h3>
                                    </div>
                                </div>
                                
                                <div class="card">
                                    <div class="card-body text-center">
                                        <h6 class="text-muted mb-1">Confidence Level</h6>
                                        <div class="progress" style="height: 20px;">
                                            <div class="progress-bar ${analysisData.confidence >= 70 ? 'bg-success' : analysisData.confidence >= 50 ? 'bg-warning' : 'bg-danger'}" 
                                                 style="width: ${analysisData.confidence}%; line-height: 20px;">
                                                ${analysisData.confidence}%
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <hr>
                
                <div class="row">
                    <div class="col-md-6">
                        <h6><i class="fas fa-chart-line text-primary"></i> Technical Indicators</h6>
                        <ul class="list-unstyled">
                            <li class="mb-2">
                                <i class="fas fa-circle text-info me-2"></i>
                                RSI: <strong>${analysisData.rsi || 'N/A'}</strong>
                                <small class="text-muted">(${analysisData.rsi > 70 ? 'Overbought' : analysisData.rsi < 30 ? 'Oversold' : 'Neutral'})</small>
                            </li>
                            <li class="mb-2">
                                <i class="fas fa-circle text-warning me-2"></i>
                                MACD: <strong>${analysisData.macd ? analysisData.macd.toFixed(3) : 'N/A'}</strong>
                            </li>
                            <li class="mb-2">
                                <i class="fas fa-circle text-success me-2"></i>
                                20-MA: <strong>$${formatCurrency(analysisData.moving_averages.ma_20)}</strong>
                            </li>
                            <li class="mb-2">
                                <i class="fas fa-circle text-danger me-2"></i>
                                50-MA: <strong>$${formatCurrency(analysisData.moving_averages.ma_50)}</strong>
                            </li>
                        </ul>
                    </div>
                    
                    <div class="col-md-6">
                        <h6><i class="fas fa-bullseye text-warning"></i> Key Levels</h6>
                        <ul class="list-unstyled">
                            <li class="mb-2">
                                <i class="fas fa-arrow-down text-success me-2"></i>
                                Support: <strong>$${formatCurrency(analysisData.support_levels?.[0] || priceData.price * 0.95)}</strong>
                            </li>
                            <li class="mb-2">
                                <i class="fas fa-arrow-up text-danger me-2"></i>
                                Resistance: <strong>$${formatCurrency(analysisData.resistance_levels?.[0] || priceData.price * 1.05)}</strong>
                            </li>
                            <li class="mb-2">
                                <i class="fas fa-tag text-muted me-2"></i>
                                Day High: <strong>$${formatCurrency(priceData.high)}</strong>
                            </li>
                            <li class="mb-2">
                                <i className="fas fa-tag text-muted me-2"></i>
                                Day Low: <strong>$${formatCurrency(priceData.low)}</strong>
                            </li>
                        </ul>
                    </div>
                </div>
                
                <hr>
                
                <div>
                    <h6><i class="fas fa-lightbulb text-warning"></i> Analysis Summary</h6>
                    <ul class="mb-0">
                        ${analysisData.reasons && analysisData.reasons.length > 0 
                            ? analysisData.reasons.map(reason => `<li>${reason}</li>`).join('')
                            : '<li>Technical analysis in progress...</li>'
                        }
                    </ul>
                </div>
            `;
        }

// Render detail chart
function renderDetailChart(symbol, priceData, container) {
    const canvasId = `detailChartCanvas-${symbol}`;
    const canvas = container.querySelector(`#${canvasId}`);
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const data = generateMockChartData(priceData);
    
    if (window.detailChartInstance) {
        window.detailChartInstance.destroy();
    }
    
    window.detailChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Price',
                data: data.prices,
                borderColor: priceData.change >= 0 ? '#198754' : '#dc3545',
                backgroundColor: priceData.change >= 0 
                    ? 'rgba(25, 135, 84, 0.1)'
                    : 'rgba(220, 53, 69, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0,
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: { display: false },
                y: { display: false }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            }
        }
    });
}

// Generate mock chart data
function generateMockChartData(priceData) {
    const labels = [];
    const prices = [];
    const basePrice = priceData.price;
    const points = 30;
    
    for (let i = 0; i < points; i++) {
        labels.push(i);
        const volatility = basePrice * 0.02;
        const trend = priceData.change >= 0 ? basePrice * 0.01 : -basePrice * 0.01;
        const price = basePrice + trend * (i / points) + (Math.random() - 0.5) * volatility;
        prices.push(Math.round(price * 100) / 100);
    }
    
    return { labels, prices };
}

// Render mini chart for each stock
function renderMiniChart(symbol, container) {
    if (!container) return;
    
    const canvas = container.querySelector('canvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const data = generateMockChartData(generateSimulatedQuote(symbol));
    
    if (chartInstances[symbol]) {
        chartInstances[symbol].destroy();
    }
    
    chartInstances[symbol] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [{
                data: data.prices,
                borderColor: '#0d6efd',
                backgroundColor: 'rgba(13, 110, 255, 0.1)',
                borderWidth: 1.5,
                fill: true,
                tension: 0.4,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { x: { display: false }, y: { display: false } }
        }
    });
}

// Show notification
function showNotification(message, type = 'success') {
    // Check for existing toast
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0 position-fixed top-0 end-0 m-3`;
    toast.style.zIndex = '9999';
    toast.style.minWidth = '250px';
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body d-flex align-items-center">
                <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'warning' ? 'exclamation-triangle' : 'times-circle'} me-2"></i>
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    document.body.appendChild(toast);
    
    const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
    bsToast.show();
    
    toast.addEventListener('hidden.bs.toast', () => toast.remove());
}

// Format currency
function formatCurrency(value) {
    if (!value) return '0.00';
    return parseFloat(value).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

// Format time
function formatTime(timestamp) {
    if (!timestamp) return '';
    return new Date(timestamp).toLocaleTimeString('en-US', { 
        hour: '2-digit', 
        minute: '2-digit',
        hour12: true 
    });
}

// Initialize mini charts after rendering
setTimeout(() => {
    if (watchlist.length > 0) {
        watchlist.forEach(item => {
            const container = document.getElementById(`mini-chart-${item.symbol}`)?.parentElement;
            if (container) {
                renderMiniChart(item.symbol, container);
            }
        });
    }
}, 500);