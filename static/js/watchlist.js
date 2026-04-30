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
        return createErrorRow(symbol);
    }
}

// Generate simulated quote data
function generateSimulatedQuote(symbol) {
    const basePrices = {
        'SPY': 450, 'QQQ': 370, 'DIA': 340, 'IWM': 190,
        'AAPL': 175, 'MSFT': 380, 'GOOGL': 135, 'AMZN': 145,
        'TSLA': 240, 'NVDA': 480, 'META': 320, 'NFLX': 420,
        'BTC-USD': 65000, 'ETH-USD': 3500, 'BNB-USD': 580, 'XRP-USD': 0.52
    };
    
    const basePrice = basePrices[symbol] || Math.random() * 100 + 20;
    const change = (Math.random() - 0.5) * 10;
    const currentPrice = basePrice * (1 + change / 100);
    const openPrice = basePrice * (1 + (Math.random() - 0.5) * 2 / 100);
    const highPrice = Math.max(openPrice, currentPrice) * (1 + Math.random() * 2 / 100);
    const lowPrice = Math.min(openPrice, currentPrice) * (1 - Math.random() * 2 / 100);
    const prevClose = basePrice;
    
    return {
        symbol: symbol,
        price: currentPrice,
        change: currentPrice - prevClose,
        change_percent: change,
        open: openPrice,
        high: highPrice,
        low: lowPrice,
        previous_close: prevClose,
        volume: Math.floor(Math.random() * 10000000) + 1000000,
        timestamp: new Date().toISOString()
    };
}

// Generate simulated analysis
function generateSimulatedAnalysis(symbol, priceData) {
    const buySuggestions = ['BUY', 'STRONG BUY'];
    const holdSuggestions = ['HOLD', 'NEUTRAL'];
    const sellSuggestions = ['SELL', 'STRONG SELL'];
    
    const suggestions = [...buySuggestions, ...buySuggestions, ...buySuggestions, ...holdSuggestions, ...holdSuggestions, ...sellSuggestions];
    const suggestion = suggestions[Math.floor(Math.random() * suggestions.length)];
    
    const confidence = Math.floor(Math.random() * 40) + 60;
    const technicalScore = Math.floor(Math.random() * 40) + 60;
    
    const reasons = {
        'BUY': ['Strong uptrend momentum', 'Bullish MACD crossover', 'Support level found', 'RSI showing strength'],
        'STRONG BUY': ['Breakout confirmed', 'Strong volume support', 'Multiple indicators bullish', 'Price above all MAs'],
        'HOLD': ['Consolidating range', 'Awaiting breakout', 'Mixed signals', 'At key resistance'],
        'NEUTRAL': ['Sideways movement', 'No clear trend', 'Balanced indicators', 'Watch for catalyst'],
        'SELL': ['Downtrend forming', 'Bearish divergence', 'Resistance strong', 'Momentum fading'],
        'STRONG SELL': ['Major breakdown', 'High volume selling', 'All indicators bearish', 'Below support']
    };
    
    const suggestionReasons = reasons[suggestion] || reasons.HOLD;
    
    return {
        symbol: symbol,
        suggestion: suggestion,
        confidence: confidence,
        technical_score: technicalScore,
        reasons: suggestionReasons,
        support_levels: [priceData.price * 0.95, priceData.price * 0.90],
        resistance_levels: [priceData.price * 1.05, priceData.price * 1.10],
        moving_averages: {
            ma_20: priceData.price * (0.98 + Math.random() * 0.04),
            ma_50: priceData.price * (0.95 + Math.random() * 0.10),
            ma_200: priceData.price * (0.90 + Math.random() * 0.20)
        },
        rsi: Math.floor(Math.random() * 60) + 20,
        macd: (Math.random() - 0.5) * 2,
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
                <br>
                <small class="text-muted">O: $${formatCurrency(priceData.open)}</small><br>
                <small class="text-muted">H: $${formatCurrency(priceData.high)}</small><br>
                <small class="text-muted">L: $${formatCurrency(priceData.low)}</small>
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
                <br>
                <small class="text-muted">
                    RSI: ${analysisData.rsi || 'N/A'}<br>
                    MACD: ${analysisData.macd ? analysisData.macd.toFixed(2) : 'N/A'}
                </small>
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
                <canvas id="mini-chart-${symbol}" width="100" height="60" class="mini-chart"></canvas>
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
    
    // Calculate summary stats
    let buyCount = 0, holdCount = 0, sellCount = 0;
    let totalScore = 0;
    let avgConfidence = 0;
    
    stocks.forEach(stock => {
        const analysis = generateSimulatedAnalysis(stock.symbol, generateSimulatedQuote(stock.symbol));
        if (analysis.suggestion.includes('BUY')) buyCount++;
        else if (analysis.suggestion.includes('SELL')) sellCount++;
        else holdCount++;
        totalScore += analysis.technical_score;
        avgConfidence += analysis.confidence;
    });
    
    avgConfidence /= stocks.length;
    const avgScore = Math.round(totalScore / stocks.length);
    
    container.innerHTML = `
        <div class="col-md-3 mb-3">
            <div class="card border-success bg-light">
                <div class="card-body text-center">
                    <h3 class="text-success mb-0">${buyCount}</h3>
                    <small class="text-muted">Buy Signals</small>
                </div>
            </div>
        </div>
        <div class="col-md-3 mb-3">
            <div class="card border-primary bg-light">
                <div class="card-body text-center">
                    <h3 class="text-primary mb-0">${holdCount}</h3>
                    <small class="text-muted">Hold Signals</small>
                </div>
            </div>
        </div>
        <div class="col-md-3 mb-3">
            <div class="card border-danger bg-light">
                <div class="card-body text-center">
                    <h3 class="text-danger mb-0">${sellCount}</h3>
                    <small class="text-muted">Sell Signals</small>
                </div>
            </div>
        </div>
        <div class="col-md-3 mb-3">
            <div class="card border-info bg-light">
                <div class="card-body text-center">
                    <h3 class="text-info mb-0">${avgScore}/100</h3>
                    <small class="text-muted">Avg Technical Score</small>
                </div>
            </div>
        </div>
        <div class="col-md-12">
            <div class="alert alert-info mb-0">
                <i class="fas fa-info-circle"></i>
                <strong>Average Confidence:</strong> ${Math.round(avgConfidence)}% | 
                <strong>Total Stocks:</strong> ${stocks.length} |
                <strong>Last Updated:</strong> ${new Date().toLocaleTimeString()}
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
        
        // Render mini chart
        setTimeout(() => renderDetailChart(symbol, priceData, bodyEl), 100);
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
            <div class="col-md-8">
                <div id="detail-chart-${symbol}" style="height: 250px; position: relative;">
                    <canvas id="detailChartCanvas-${symbol}"></canvas>
                </div>
            </div>
            <div class="col-md-4">
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