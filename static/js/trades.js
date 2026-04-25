// Crypto Scanner - Trades Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    loadOpenTrades();
    loadTradeHistory();
    
    // Setup filter handlers
    document.getElementById('strategy-filter').addEventListener('change', loadTradeHistory);
    document.getElementById('outcome-filter').addEventListener('change', loadTradeHistory);
    document.getElementById('days-filter').addEventListener('change', loadTradeHistory);
    
    // Refresh open trades every minute
    setInterval(loadOpenTrades, 60000);
});

// Load open trades
function loadOpenTrades() {
    fetch('/api/trades/open')
        .then(r => r.json())
        .then(data => {
            document.getElementById('open-count').textContent = data.count;
            updateOpenTradesTable(data.trades);
        })
        .catch(error => console.error('Error loading open trades:', error));
}

// Update open trades table
function updateOpenTradesTable(trades) {
    const tbody = document.getElementById('open-trades-table');
    
    if (!trades || trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">No open trades</td></tr>';
        return;
    }
    
    tbody.innerHTML = trades.map(trade => {
        const targets = trade.targets || [];
        const unrealizedPnl = trade.unrealized_pnl || 0;
        const unrealizedPct = trade.unrealized_pnl_pct || 0;
        const pnlClass = unrealizedPnl >= 0 ? 'text-success' : 'text-danger';
        
        return `
            <tr onclick="openTradeDetails('${trade.trade_id}')">
                <td><strong>${trade.symbol}</strong></td>
                <td><span class="badge bg-info">${trade.strategy}</span></td>
                <td>$${formatPrice(trade.entry)}</td>
                <td>$${formatPrice(trade.current_price || trade.entry)}</td>
                <td>$${formatPrice(trade.stop_loss)}</td>
                <td>${targets.map(t => '$' + formatPrice(t)).join(' / ')}</td>
                <td class="${pnlClass}"><strong>$${formatCurrency(unrealizedPnl)}</strong></td>
                <td class="${pnlClass}">${unrealizedPct.toFixed(2)}%</td>
                <td>${Math.abs(trade.distance_to_sl || 0).toFixed(2)}</td>
                <td>${Math.floor(trade.holding_days || 0)} days</td>
            </tr>
        `;
    }).join('');
}

// Load trade history
function loadTradeHistory() {
    const strategy = document.getElementById('strategy-filter').value;
    const outcome = document.getElementById('outcome-filter').value;
    const days = document.getElementById('days-filter').value;
    
    let url = '/api/trades/history?limit=100';
    if (strategy) url += '&strategy=' + strategy;
    if (outcome) url += '&outcome=' + outcome;
    if (days) url += '&days=' + days;
    
    fetch(url)
        .then(r => r.json())
        .then(data => {
            document.getElementById('history-count').textContent = data.count;
            updateHistoryTable(data.trades);
        })
        .catch(error => console.error('Error loading trade history:', error));
}

// Update history table
function updateHistoryTable(trades) {
    const tbody = document.getElementById('history-table');
    
    if (!trades || trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="11" class="text-center text-muted">No trades found</td></tr>';
        return;
    }
    
    tbody.innerHTML = trades.map(trade => {
        const outcome = trade.outcome || 'OPEN';
        const outcomeColor = outcome === 'WIN' ? 'bg-success' : outcome === 'LOSS' ? 'bg-danger' : 'bg-secondary';
        const quality = trade.quality || 'B';
        
        const exitPrice = trade.targets && trade.targets.length > 0 
            ? trade.targets[Math.min((trade.highest_target_hit || 1) - 1, trade.targets.length - 1)]
            : trade.entry;
        
        return `
            <tr onclick="viewTradeDetails('${trade.trade_id}')">
                <td><code>${trade.trade_id.substring(0, 8)}</code></td>
                <td><strong>${trade.symbol}</strong></td>
                <td><span class="badge bg-primary">${trade.strategy}</span></td>
                <td>$${formatPrice(trade.entry)}</td>
                <td>$${formatPrice(exitPrice)}</td>
                <td>$${formatPrice(trade.stop_loss)}</td>
                <td><span class="badge ${outcomeColor}">${outcome}</span></td>
                <td class="${outcome === 'WIN' ? 'text-success' : outcome === 'LOSS' ? 'text-danger' : ''}">
                    $${formatCurrency((exitPrice - trade.entry) * (trade.quantity || 1))}
                </td>
                <td>${trade.rr_achieved.toFixed(2)}</td>
                <td>${Math.floor(trade.holding_days || 0)}</td>
                <td><span class="badge bg-warning">${quality}</span></td>
            </tr>
        `;
    }).join('');
}

// View trade details modal
function viewTradeDetails(tradeId) {
    fetch('/api/trades/' + tradeId)
        .then(r => r.json())
        .then(trade => {
            const modal = createTradeDetailsModal(trade);
            document.body.appendChild(modal);
            new bootstrap.Modal(modal).show();
        })
        .catch(error => alert('Error loading trade details: ' + error));
}

// Create trade details modal
function createTradeDetailsModal(trade) {
    const div = document.createElement('div');
    div.className = 'modal fade';
    div.innerHTML = `
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Trade Details - ${trade.symbol}</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <label class="small text-muted">Trade ID</label>
                            <p><code>${trade.trade_id}</code></p>
                        </div>
                        <div class="col-md-6">
                            <label class="small text-muted">Status</label>
                            <p><span class="badge ${trade.outcome === 'WIN' ? 'bg-success' : 'bg-danger'}">${trade.outcome}</span></p>
                        </div>
                    </div>

                    <div class="row mb-3">
                        <div class="col-md-3">
                            <label class="small text-muted">Entry</label>
                            <p>$${formatPrice(trade.entry)}</p>
                        </div>
                        <div class="col-md-3">
                            <label class="small text-muted">Stop Loss</label>
                            <p>$${formatPrice(trade.stop_loss)}</p>
                        </div>
                        <div class="col-md-3">
                            <label class="small text-muted">RR Achieved</label>
                            <p>${trade.rr_achieved.toFixed(2)}</p>
                        </div>
                        <div class="col-md-3">
                            <label class="small text-muted">Holding Days</label>
                            <p>${Math.floor(trade.holding_days || 0)}</p>
                        </div>
                    </div>

                    <div class="row mb-3">
                        <div class="col-md-12">
                            <label class="small text-muted">Targets</label>
                            <p>${(trade.targets || []).map((t, i) => {
                                const hit = trade.targets_hit && trade.targets_hit.includes(i + 1);
                                return `<span class="badge ${hit ? 'bg-success' : 'bg-secondary'}">T${i+1}: $${formatPrice(t)}</span>`;
                            }).join(' ')}</p>
                        </div>
                    </div>

                    <div class="row mb-3">
                        <div class="col-md-4">
                            <label class="small text-muted">Strategy</label>
                            <p>${trade.strategy}</p>
                        </div>
                        <div class="col-md-4">
                            <label class="small text-muted">Market Context</label>
                            <p>${trade.market_context}</p>
                        </div>
                        <div class="col-md-4">
                            <label class="small text-muted">Quality</label>
                            <p><span class="badge bg-warning">${trade.quality || 'B'}</span></p>
                        </div>
                    </div>

                    <hr>

                    <h6>Trade Metrics</h6>
                    <div class="row">
                        <div class="col-md-4">
                            <p><small class="text-muted">Volume Ratio</small><br>${trade.volume_ratio.toFixed(2)}</p>
                        </div>
                        <div class="col-md-4">
                            <p><small class="text-muted">RSI</small><br>${trade.rsi.toFixed(2)}</p>
                        </div>
                        <div class="col-md-4">
                            <p><small class="text-muted">Max Drawdown</small><br>$${formatCurrency(trade.max_drawdown)}</p>
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                </div>
            </div>
        </div>
    `;
    return div;
}

// Utility functions
function formatPrice(price) {
    if (!price) return '0.00';
    return parseFloat(price).toFixed(2);
}

function formatCurrency(value) {
    if (!value) return '0.00';
    return Math.abs(value).toFixed(2);
}
