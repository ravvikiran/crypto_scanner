// Crypto Scanner - Analysis Page JavaScript

let sectorChart = null;
let signalsChart = null;

document.addEventListener('DOMContentLoaded', function() {
    loadMarketSentiment();
    initCharts();
    loadSignalsData();
    
    // Refresh every 5 minutes
    setInterval(loadMarketSentiment, 300000);
});

// Load market sentiment
function loadMarketSentiment() {
    fetch('/api/analysis/market-sentiment')
        .then(r => r.json())
        .then(data => {
            updateSentimentDisplay(data);
        })
        .catch(error => console.error('Error loading sentiment:', error));
}

// Update sentiment display
function updateSentimentDisplay(data) {
    const trendColor = {
        'BULLISH': 'bg-success',
        'BEARISH': 'bg-danger',
        'SIDEWAYS': 'bg-warning'
    };
    
    const btcTrend = data.btc_trend || data.nifty_trend || 'SIDEWAYS';
    document.getElementById('sentiment-btc').innerHTML = 
        `<span class="badge ${trendColor[btcTrend]}">${btcTrend}</span>`;
    
    document.getElementById('sentiment-strength').style.width = data.market_strength + '%';
    document.getElementById('sentiment-strength-text').textContent = data.market_strength + '%';
    
    const volColor = {
        'LOW': 'bg-info',
        'NORMAL': 'bg-success',
        'HIGH': 'bg-danger'
    };
    
    document.getElementById('sentiment-volatility').innerHTML = 
        `<span class="badge ${volColor[data.volatility]}">${data.volatility}</span>`;
    
    document.getElementById('sentiment-time').textContent = 
        new Date(data.timestamp).toLocaleTimeString();
    
    // Update sector chart
    updateSectorChart(data.sector_leaders || []);
}

// Initialize charts
function initCharts() {
    // Sector performance chart
    const sectorCtx = document.getElementById('sectorChart').getContext('2d');
    sectorChart = new Chart(sectorCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Sector Strength',
                data: [],
                backgroundColor: 'rgba(13, 110, 253, 0.7)',
                borderColor: '#0d6efd',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            indexAxis: 'y',
            plugins: {
                legend: {
                    display: true
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    max: 100
                }
            }
        }
    });
    
    // Signals distribution chart
    const signalsCtx = document.getElementById('signalsChart').getContext('2d');
    signalsChart = new Chart(signalsCtx, {
        type: 'doughnut',
        data: {
            labels: ['Today', 'This Week', 'This Month'],
            datasets: [{
                data: [0, 0, 0],
                backgroundColor: [
                    'rgba(13, 110, 253, 0.8)',
                    'rgba(25, 135, 84, 0.8)',
                    'rgba(220, 53, 69, 0.8)'
                ],
                borderColor: ['#fff', '#fff', '#fff'],
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    });
}

// Update sector chart
function updateSectorChart(sectors) {
    if (sectorChart && sectors.length > 0) {
        sectorChart.data.labels = sectors.map(s => s.sector);
        sectorChart.data.datasets[0].data = sectors.map(s => s.strength);
        sectorChart.update();
    }
}

// Load signals data
function loadSignalsData() {
    fetch('/api/analysis/signals-generated?days=30')
        .then(r => r.json())
        .then(data => {
            updateSignalsTable(data.signals_by_day);
            updateSignalsChart(data);
            loadTopStocks();
        })
        .catch(error => console.error('Error loading signals:', error));
}

// Update signals table
function updateSignalsTable(signalsByDay) {
    const tbody = document.getElementById('signals-table');
    
    if (!signalsByDay || Object.keys(signalsByDay).length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No signals data</td></tr>';
        return;
    }
    
    // Sort by date descending
    const sortedDates = Object.keys(signalsByDay).sort().reverse();
    
    tbody.innerHTML = sortedDates.slice(0, 30).map(date => {
        const dayData = signalsByDay[date];
        const winRate = dayData.count > 0 
            ? ((dayData.wins / dayData.count) * 100).toFixed(2) 
            : '0.00';
        
        return `
            <tr>
                <td>${new Date(date).toLocaleDateString()}</td>
                <td><strong>${dayData.count}</strong></td>
                <td><span class="text-success">${dayData.wins}</span></td>
                <td><span class="text-danger">${dayData.losses}</span></td>
                <td><span class="badge bg-primary">${winRate}%</span></td>
            </tr>
        `;
    }).join('');
}

// Update signals chart
function updateSignalsChart(data) {
    const today = new Date().toISOString().split('T')[0];
    const weekAgo = new Date(Date.now() - 7*24*60*60*1000).toISOString().split('T')[0];
    const monthAgo = new Date(Date.now() - 30*24*60*60*1000).toISOString().split('T')[0];
    
    let todayCount = 0, weekCount = 0, monthCount = 0;
    
    Object.entries(data.signals_by_day).forEach(([date, dayData]) => {
        const count = dayData.count;
        if (date === today) todayCount = count;
        if (date >= weekAgo) weekCount += count;
        if (date >= monthAgo) monthCount += count;
    });
    
    if (signalsChart) {
        signalsChart.data.datasets[0].data = [todayCount, weekCount - todayCount, monthCount - weekCount];
        signalsChart.update();
    }
}

// Load top performing stocks
function loadTopStocks() {
    fetch('/api/trades/history?limit=500')
        .then(r => r.json())
        .then(data => {
            const stockStats = {};
            
            // Aggregate stats by stock
            data.trades.forEach(trade => {
                if (!stockStats[trade.symbol]) {
                    stockStats[trade.symbol] = {
                        total: 0,
                        wins: 0,
                        losses: 0,
                        totalProfit: 0,
                        totalLoss: 0
                    };
                }
                
                const stat = stockStats[trade.symbol];
                stat.total++;
                
                if (trade.outcome === 'WIN') {
                    stat.wins++;
                    const targets = trade.targets || [];
                    if (targets.length > 0) {
                        stat.totalProfit += targets[0] - trade.entry;
                    }
                } else if (trade.outcome === 'LOSS') {
                    stat.losses++;
                    stat.totalLoss += trade.entry - trade.stop_loss;
                }
            });
            
            // Sort by win rate and limit to top 10
            const sorted = Object.entries(stockStats)
                .map(([symbol, stat]) => ({
                    symbol,
                    ...stat,
                    winRate: (stat.wins / stat.total * 100).toFixed(2),
                    avgProfit: stat.wins > 0 ? (stat.totalProfit / stat.wins).toFixed(2) : 0,
                    avgLoss: stat.losses > 0 ? (stat.totalLoss / stat.losses).toFixed(2) : 0
                }))
                .sort((a, b) => parseFloat(b.winRate) - parseFloat(a.winRate))
                .slice(0, 10);
            
            updateTopStocksTable(sorted);
        });
}

// Update top stocks table
function updateTopStocksTable(stocks) {
    const tbody = document.getElementById('top-stocks-table');
    
    if (!stocks || stocks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No stock data</td></tr>';
        return;
    }
    
    tbody.innerHTML = stocks.map(stock => `
        <tr>
            <td><strong>${stock.symbol}</strong></td>
            <td>${stock.total}</td>
            <td><span class="text-success">${stock.wins}</span></td>
            <td><span class="badge bg-success">${stock.winRate}%</span></td>
            <td>$${formatCurrency(stock.avgProfit)}</td>
            <td>$${formatCurrency(stock.avgLoss)}</td>
        </tr>
    `).join('');
}

// Utility function
function formatCurrency(value) {
    if (!value) return '0.00';
    return Math.abs(value).toFixed(2);
}
