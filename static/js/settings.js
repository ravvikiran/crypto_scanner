// Crypto Scanner - Settings Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    loadSettings();
    setupRangeSliders();
});

// Load settings from API
function loadSettings() {
    fetch('/api/settings')
        .then(r => r.json())
        .then(data => {
            populateSettings(data);
        })
        .catch(error => console.error('Error loading settings:', error));
}

// Populate form fields with settings data
function populateSettings(settings) {
    // General settings
    if (settings.scanner_name) {
        document.getElementById('scanner-name').value = settings.scanner_name;
    }
    if (settings.scan_interval) {
        document.getElementById('scan-interval').value = settings.scan_interval;
    }
    if (settings.default_qty) {
        document.getElementById('default-qty').value = settings.default_qty;
    }
    if (settings.risk_per_trade) {
        document.getElementById('risk-per-trade').value = settings.risk_per_trade;
    }
    
    // Strategy weights
    if (settings.strategy_weights) {
        const weights = settings.strategy_weights;
        document.getElementById('trend-weight').value = weights.TREND || 30;
        document.getElementById('verc-weight').value = weights.VERC || 25;
        document.getElementById('mtf-weight').value = weights.MTF || 20;
        document.getElementById('swing-weight').value = weights.SWING || 25;
    }
    
    // Trend parameters
    if (settings.trend_params) {
        document.getElementById('min-vol-ratio').value = settings.trend_params.min_volume_ratio || 1.5;
        document.getElementById('min-rsi').value = settings.trend_params.min_rsi || 50;
        document.getElementById('max-rsi').value = settings.trend_params.max_rsi || 65;
    }
    
    // Position management
    if (settings.position_management) {
        document.getElementById('sl-pct').value = settings.position_management.stop_loss_pct || 2.5;
        document.getElementById('t1-pct').value = settings.position_management.target1_pct || 5;
        document.getElementById('t2-pct').value = settings.position_management.target2_pct || 8;
    }
    
    // Alerts
    if (settings.alerts) {
        document.getElementById('alert-telegram').checked = settings.alerts.telegram !== false;
        document.getElementById('alert-email').checked = settings.alerts.email || false;
        document.getElementById('min-confidence').value = settings.alerts.min_confidence || 50;
        document.getElementById('alert-sound').value = settings.alerts.sound || 'bell';
    }
    
    // Advanced settings
    if (settings.advanced) {
        document.getElementById('max-open-trades').value = settings.advanced.max_open_trades || 5;
        document.getElementById('trade-timeout').value = settings.advanced.trade_timeout_days || 15;
        document.getElementById('auto-optimize').checked = settings.advanced.auto_optimize !== false;
        document.getElementById('ai-learning').checked = settings.advanced.ai_learning !== false;
        document.getElementById('log-level').value = settings.advanced.log_level || 'INFO';
    }
}

// Setup range slider event listeners
function setupRangeSliders() {
    const sliders = [
        { id: 'trend-weight', display: 'trend-weight-val' },
        { id: 'verc-weight', display: 'verc-weight-val' },
        { id: 'mtf-weight', display: 'mtf-weight-val' },
        { id: 'swing-weight', display: 'swing-weight-val' },
        { id: 'min-confidence', display: 'confidence-val' }
    ];
    
    sliders.forEach(slider => {
        const elem = document.getElementById(slider.id);
        if (elem) {
            elem.addEventListener('input', function() {
                document.getElementById(slider.display).textContent = this.value + '%';
            });
        }
    });
}

// Save general settings
function saveGeneralSettings() {
    const settings = {
        scanner_name: document.getElementById('scanner-name').value,
        scan_interval: parseInt(document.getElementById('scan-interval').value),
        default_qty: parseInt(document.getElementById('default-qty').value),
        risk_per_trade: parseFloat(document.getElementById('risk-per-trade').value)
        // skip_weekends: removed for 24/7 crypto markets
    };
    
    saveSettings(settings, 'General settings saved successfully!');
}

// Save strategy settings
function saveStrategySettings() {
    const settings = {
        strategy_weights: {
            TREND: parseInt(document.getElementById('trend-weight').value),
            VERC: parseInt(document.getElementById('verc-weight').value),
            MTF: parseInt(document.getElementById('mtf-weight').value),
            SWING: parseInt(document.getElementById('swing-weight').value)
        },
        trend_params: {
            min_volume_ratio: parseFloat(document.getElementById('min-vol-ratio').value),
            min_rsi: parseInt(document.getElementById('min-rsi').value),
            max_rsi: parseInt(document.getElementById('max-rsi').value)
        },
        position_management: {
            stop_loss_pct: parseFloat(document.getElementById('sl-pct').value),
            target1_pct: parseFloat(document.getElementById('t1-pct').value),
            target2_pct: parseFloat(document.getElementById('t2-pct').value)
        }
    };
    
    saveSettings(settings, 'Strategy settings saved successfully!');
}

// Save API settings
function saveAPISettings() {
    const settings = {
        api_keys: {
            telegram_token: document.getElementById('telegram-token').value,
            telegram_chat: document.getElementById('telegram-chat').value,
            openai_key: maskSensitive(document.getElementById('openai-key').value),
            groq_key: maskSensitive(document.getElementById('groq-key').value)
        }
    };
    
    saveSettings(settings, 'API keys saved successfully!');
}

// Save alert settings
function saveAlertSettings() {
    const settings = {
        alerts: {
            telegram: document.getElementById('alert-telegram').checked,
            email: document.getElementById('alert-email').checked,
            min_confidence: parseInt(document.getElementById('min-confidence').value),
            sound: document.getElementById('alert-sound').value
        }
    };
    
    saveSettings(settings, 'Alert settings saved successfully!');
}

// Save advanced settings
function saveAdvancedSettings() {
    const settings = {
        advanced: {
            max_open_trades: parseInt(document.getElementById('max-open-trades').value),
            trade_timeout_days: parseInt(document.getElementById('trade-timeout').value),
            auto_optimize: document.getElementById('auto-optimize').checked,
            ai_learning: document.getElementById('ai-learning').checked,
            log_level: document.getElementById('log-level').value
        }
    };
    
    saveSettings(settings, 'Advanced settings saved successfully!');
}

// Generic save settings function
function saveSettings(data, message) {
    fetch('/api/settings', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(r => r.json())
    .then(response => {
        if (response.success) {
            showNotification(message, 'success');
        } else {
            showNotification('Error: ' + response.error, 'error');
        }
    })
    .catch(error => {
        showNotification('Error saving settings: ' + error, 'error');
    });
}

// Reset all settings
function resetAllSettings() {
    if (confirm('Are you sure you want to reset all settings to defaults? This cannot be undone!')) {
        // In real implementation, would call API to reset
        showNotification('Settings would be reset to defaults', 'info');
    }
}

// Clear trade history
function clearTradeHistory() {
    if (confirm('Are you sure you want to clear all trade history? This cannot be undone!')) {
        // In real implementation, would call API to clear
        showNotification('Trade history would be cleared', 'info');
    }
}

// Utility functions
function maskSensitive(value) {
    if (!value) return '';
    if (value.length <= 8) return value;
    return value.substring(0, 4) + '****' + value.substring(value.length - 4);
}

function showNotification(message, type = 'info') {
    const alertClass = {
        'success': 'alert-success',
        'error': 'alert-danger',
        'info': 'alert-info',
        'warning': 'alert-warning'
    }[type] || 'alert-info';
    
    const alert = document.createElement('div');
    alert.className = `alert ${alertClass} alert-dismissible fade show`;
    alert.role = 'alert';
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // Insert at top of page
    document.querySelector('.container-fluid').insertBefore(
        alert,
        document.querySelector('.container-fluid').firstChild
    );
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        alert.remove();
    }, 5000);
}

// Export settings
function exportSettings() {
    fetch('/api/settings')
        .then(r => r.json())
        .then(data => {
            const dataStr = JSON.stringify(data, null, 2);
            const dataBlob = new Blob([dataStr], { type: 'application/json' });
            const url = URL.createObjectURL(dataBlob);
            const link = document.createElement('a');
            link.href = url;
            link.download = 'crypto-scanner-settings.json';
            link.click();
        });
}

// Import settings
function importSettings(file) {
    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            const data = JSON.parse(e.target.result);
            saveSettings(data, 'Settings imported successfully!');
        } catch (error) {
            showNotification('Error parsing settings file: ' + error, 'error');
        }
    };
    reader.readAsText(file);
}
