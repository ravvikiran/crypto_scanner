// Crypto Scanner - Performance Page JavaScript

let strategyChart = null;
let pnlCurveChart = null;
let winLossDistChart = null;

document.addEventListener('DOMContentLoaded', function() {
    loadPerformanceSummary();
    initCharts();
    loadStrategyPerformance();
    
    // Refresh every minute
    setInterval(loadPerformanceSummary, 60000);
});

// Load performance summary
function loadPerformanceSummary() {
    fetch('/api/performance/summary')
        .then(r => r.json())
        .then(data => {
            document.getElementById('perf-total').textContent = data.total_trades;
            document.getElementById('perf-win-rate').textContent = data.win_rate.toFixed(2) + '%';
            document.getElementById('perf-win-count').textContent = `${data.win_count}W / ${data.loss_count}L`;
            document.getElementById('perf-pf').textContent = data.profit_factor.toFixed(2);
            document.getElementById('perf-rr').textContent = data.avg_rr.toFixed(2);
            document.getElementById('perf-total-pnl').textContent = '$' + formatCurrency(data.total_pnl);
            document.getElementById('perf-gross-profit').textContent = '$' + formatCurrency(data.gross_profit);
            document.getElementById('perf-gross-loss').textContent = '$' + formatCurrency(Math.abs(data.gross_loss));
            document.getElementById('perf-max-dd').textContent = '$' + formatCurrency(Math.abs(data.max_drawdown));
            
            // Update colors
            const pnlElement = document.getElementById('perf-total-pnl');
            pnlElement.style.color = data.total_pnl >= 0 ? '#198754' : '#dc3545';
            
            updateWinLossDistChart(data);
        })
        .catch(error => console.error('Error loading performance summary:', error));
}

// Initialize charts
function initCharts() {
    // Strategy performance chart
    const strategyCtx = document.getElementById('strategyChart').getContext('2d');
    strategyChart = new Chart(strategyCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Win Rate %',
                    data: [],
                    backgroundColor: 'rgba(25, 135, 84, 0.7)',
                    borderColor: '#198754',
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            indexAxis: 'y',
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
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
    
    // P&L Curve chart
    const pnlCtx = document.getElementById('pnlCurveChart').getContext('2d');
    pnlCurveChart = new Chart(pnlCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Cumulative P&L',
                data: [],
                borderColor: '#0d6efd',
                backgroundColor: 'rgba(13, 110, 253, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 1,
                pointBackgroundColor: '#0d6efd'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            scales: {
                y: {
                    ticks: {
                        callback: function(value) {
                            return '$' + formatCurrency(value);
                        }
                    }
                }
            }
        }
    });
    
    // Win vs Loss Distribution
    const winLossCtx = document.getElementById('winLossDistChart').getContext('2d');
    winLossDistChart = new Chart(winLossCtx, {
        type: 'doughnut',
        data: {
            labels: ['Wins', 'Losses'],
            datasets: [{
                data: [0, 0],
                backgroundColor: ['#198754', '#dc3545'],
                borderColor: ['#fff', '#fff'],
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

// Update win/loss distribution chart
function updateWinLossDistChart(data) {
    if (winLossDistChart) {
        winLossDistChart.data.datasets[0].data = [data.win_count, data.loss_count];
        winLossDistChart.update();
    }
    
    // Load and update P&L curve
    loadPnlCurve();
}

// Load P&L curve data
function loadPnlCurve() {
    fetch('/api/performance/pnl-curve')
        .then(r => r.json())
        .then(data => {
            if (pnlCurveChart && data.length > 0) {
                pnlCurveChart.data.labels = data.map(d => 
                    new Date(d.timestamp).toLocaleDateString()
                );
                pnlCurveChart.data.datasets[0].data = data.map(d => d.cumulative_pnl);
                pnlCurveChart.update();
            }
        });
}

// Load strategy performance breakdown
function loadStrategyPerformance() {
    fetch('/api/performance/by-strategy')
        .then(r => r.json())
        .then(data => {
            updateStrategyChart(data);
            updateStrategyTable(data);
        })
        .catch(error => console.error('Error loading strategy performance:', error));
}

// Update strategy chart
function updateStrategyChart(strategies) {
    const labels = Object.keys(strategies);
    const winRates = labels.map(s => strategies[s].win_rate);
    
    if (strategyChart) {
        strategyChart.data.labels = labels;
        strategyChart.data.datasets[0].data = winRates;
        strategyChart.update();
    }
}

// Update strategy table
function updateStrategyTable(strategies) {
    const tbody = document.getElementById('strategy-table');
    
    if (!strategies || Object.keys(strategies).length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No strategy data</td></tr>';
        return;
    }
    
    tbody.innerHTML = Object.entries(strategies).map(([strategy, data]) => `
        <tr>
            <td><strong>${strategy}</strong></td>
            <td>${data.total_trades}</td>
            <td><span class="text-success">${data.win_count}</span></td>
            <td><span class="text-danger">${data.loss_count}</span></td>
            <td><span class="badge bg-primary">${data.win_rate.toFixed(2)}%</span></td>
            <td>${data.avg_rr.toFixed(2)}</td>
            <td>
                <button class="btn btn-sm btn-outline-primary" onclick="viewStrategyDetails('${strategy}')">
                    <i class="fas fa-chart-bar"></i> View
                </button>
            </td>
        </tr>
    `).join('');
}

// View strategy details (placeholder)
function viewStrategyDetails(strategy) {
    alert('Strategy details for ' + strategy);
}

// Utility function
function formatCurrency(value) {
    if (!value) return '0.00';
    return Math.abs(value).toFixed(2);
}
