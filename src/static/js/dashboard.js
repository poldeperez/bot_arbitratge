class Dashboard {
    constructor() {
        this.currentLogFile = null;
        this.refreshInterval = null;
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.startAutoRefresh();
        this.loadInitialData();
    }
    
    setupEventListeners() {
        // Refresh button
        const refreshBtn = document.querySelector('.refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshAll());
        }
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'r') {
                e.preventDefault();
                this.refreshAll();
            }
        });
    }
    
    async loadInitialData() {
        await this.fetchStatus();
        await this.fetchLogFiles();
    }
    
    async fetchStatus() {
        try {
            const response = await fetch('/api/status');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            this.updateExchangeStatus(data.exchanges);
            this.updateErrorCount(data.error_count);
            this.updateRecentErrors(data.recent_errors);
            this.updateOpportunities(data.opportunities);
            this.updateLastUpdate(data.timestamp);
            
        } catch (error) {
            console.error('Error fetching status:', error);
            this.showError('Error loading status data');
        }
    }
    
    async fetchLogFiles() {
        try {
            const response = await fetch('/api/logs');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            this.updateLogTabs(data.files);
            
            // Load first log file if none selected
            if (data.files.length > 0 && !this.currentLogFile) {
                this.loadLogFile(data.files[0]);
            }
            
        } catch (error) {
            console.error('Error fetching log files:', error);
            this.showError('Error loading log files');
        }
    }
    
    async loadLogFile(filename) {
        if (!filename || !this.isValidLogFile(filename)) {
            console.error('Invalid log filename:', filename);
            return;
        }
        
        this.currentLogFile = filename;
        this.updateActiveTab(filename);
        
        try {
            const response = await fetch(`/api/logs/${encodeURIComponent(filename)}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            this.updateLogsContent(data.lines);
            
        } catch (error) {
            console.error('Error loading log file:', error);
            this.showError(`Error loading log file: ${filename}`);
        }
    }
    
    updateExchangeStatus(exchanges) {
        const container = document.getElementById('exchange-status');
        if (!container) return;
        
        if (!exchanges || Object.keys(exchanges).length === 0) {
            container.innerHTML = '<div class="no-data">No exchange data available</div>';
            return;
        }
        
        const statusHtml = Object.entries(exchanges)
            .map(([name, status]) => 
                `<div class="status-${status}">
                    ${name.charAt(0).toUpperCase() + name.slice(1)}: ${status}
                </div>`
            ).join('');
        
        container.innerHTML = statusHtml;
    }
    
    updateErrorCount(errorCount) {
        const container = document.getElementById('error-count');
        if (!container) return;
        
        if (!errorCount || Object.keys(errorCount).length === 0) {
            container.innerHTML = '<div class="no-data">No errors found</div>';
            return;
        }
        
        const errorHtml = Object.entries(errorCount)
            .sort(([,a], [,b]) => b - a) // Sort by count descending
            .map(([key, count]) => 
                `<div class="error-item">
                    <span>${key}</span>
                    <span class="error-count">${count} errors</span>
                </div>`
            ).join('');
        
        container.innerHTML = errorHtml;
    }
    
    updateRecentErrors(errors) {
        const container = document.getElementById('recent-errors');
        if (!container) return;
        
        if (!errors || errors.length === 0) {
            container.innerHTML = '<div class="no-data">No recent errors</div>';
            return;
        }
        
        const errorsHtml = errors
            .slice(-10) // Last 10 errors
            .reverse() // Most recent first
            .map(error => 
                `<div class="error-entry">
                    <div class="error-timestamp">${error.timestamp} - ${error.crypto} (${error.exchange})</div>
                    <div class="error-message">${this.truncateText(error.message, 120)}</div>
                </div>`
            ).join('');
        
        container.innerHTML = errorsHtml;
    }

    updateOpportunities(opportunitiesData) {
        this.updateOpportunitiesSummary(opportunitiesData);
        this.updateRecentOpportunities(opportunitiesData.recent_opportunities);
    }
    
    updateOpportunitiesSummary(data) {
        const container = document.getElementById('opportunities-summary');
        if (!container) return;
        
        const { by_symbol, total_count, total_profit } = data;
        
        if (!by_symbol || Object.keys(by_symbol).length === 0) {
            container.innerHTML = '<div class="no-data">No opportunities found in the last 24 hours</div>';
            return;
        }
        
        const summaryHtml = Object.entries(by_symbol)
            .sort(([,a], [,b]) => b.count - a.count)  // Ordenar por cantidad
            .map(([symbol, data]) => 
                `<div class="opportunity-item">
                    <div class="opportunity-count">${data.count}</div>
                    <div class="opportunity-symbol">${symbol}</div>
                    <div class="opportunity-profit">
                        Best: ${data.best_profit.toFixed(2)} USDT<br>
                        Total: ${data.total_profit.toFixed(2)} USDT
                    </div>
                </div>`
            ).join('');
        
        // Agregar total
        const totalHtml = `
            <div class="opportunity-item" style="background: linear-gradient(135deg, #007bff 0%, #6f42c1 100%);">
                <div class="opportunity-count">${total_count}</div>
                <div class="opportunity-symbol">TOTAL</div>
                <div class="opportunity-profit">
                    ${total_profit.toFixed(2)} USDT<br>
                    ${Object.keys(by_symbol).length} symbols
                </div>
            </div>`;
        
        container.innerHTML = summaryHtml + totalHtml;
    }

    updateRecentOpportunities(opportunities) {
        const container = document.getElementById('recent-opportunities');
        if (!container) return;
        
        if (!opportunities || opportunities.length === 0) {
            container.innerHTML = '<div class="no-data">No recent opportunities</div>';
            return;
        }
        
        const opportunitiesHtml = opportunities
            .slice(0, 10)  // Solo últimas 10
            .map(opp => 
                `<div class="opportunity-entry">
                    <div class="opportunity-timestamp">${opp.timestamp} - ${opp.symbol}</div>
                    <div class="opportunity-details">
                        Profit: ${opp.profit.toFixed(2)} USDT (${opp.spread_pct}%)
                    </div>
                    <div class="opportunity-trade">
                        Buy ${opp.buy_exchange} at ${opp.buy_price} → Sell ${opp.sell_exchange} at ${opp.sell_price}
                    </div>
                </div>`
            ).join('');
        
        container.innerHTML = opportunitiesHtml;
    }
    
    updateLogTabs(files) {
        const container = document.getElementById('log-tabs');
        if (!container) return;
        
        if (!files || files.length === 0) {
            container.innerHTML = '<div class="no-data">No log files found</div>';
            return;
        }
        
        const tabsHtml = files
            .map(file => 
                `<button class="tab" onclick="dashboard.loadLogFile('${file}')" data-file="${file}">
                    ${file}
                </button>`
            ).join('');
        
        container.innerHTML = tabsHtml;
    }
    
    updateActiveTab(filename) {
        const tabs = document.querySelectorAll('.tab');
        tabs.forEach(tab => {
            const isActive = tab.dataset.file === filename;
            tab.classList.toggle('active', isActive);
        });
    }
    
    updateLogsContent(lines) {
        const container = document.getElementById('logs-content');
        if (!container) return;
        
        if (!lines || lines.length === 0) {
            container.innerHTML = '<div class="no-data">No log data available</div>';
            return;
        }
        
        const logsHtml = lines
            .map(line => {
                const className = this.getLogLineClass(line);
                const escapedLine = this.escapeHtml(line);
                return `<div class="${className}">${escapedLine}</div>`;
            }).join('');
        
        container.innerHTML = logsHtml;
        
        // Auto-scroll to bottom
        container.scrollTop = container.scrollHeight;
    }
    
    updateLastUpdate(timestamp) {
        const container = document.getElementById('last-update');
        if (!container) return;
        
        const date = new Date(timestamp);
        container.textContent = `Last update: ${date.toLocaleTimeString()}`;
    }
    
    getLogLineClass(line) {
        // Regex para verificar que la línea empiece con timestamp (YYYY-MM-DD HH:MM:SS)
        const timestampRegex = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/;
        
        // Solo aplicar clases si la línea tiene timestamp válido
        if (timestampRegex.test(line)) {
            const lineUpper = line.toUpperCase();
            
            if (lineUpper.includes('ERROR')) return 'error-line';
            if (lineUpper.includes('WARNING') || lineUpper.includes('WARN')) return 'warning-line';
            if (lineUpper.includes('INFO')) return 'info-line';
            if (lineUpper.includes('SUCCESS') || lineUpper.includes('CONNECTED')) return 'success-line';
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    truncateText(text, maxLength) {
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }
    
    isValidLogFile(filename) {
        return /^[\w\-_.]+\.log$/.test(filename);
    }
    
    refreshAll() {
        console.log('Refreshing all data...');
        this.fetchStatus();
        if (this.currentLogFile) {
            this.loadLogFile(this.currentLogFile);
        }
    }
    
    startAutoRefresh() {
        // Refresh every 30 seconds
        this.refreshInterval = setInterval(() => {
            this.refreshAll();
        }, 30000);
    }
    
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }
    
    showError(message) {
        console.error(message);
        // You could implement a toast notification system here
        const errorDiv = document.createElement('div');
        errorDiv.className = 'flash flash-error';
        errorDiv.textContent = message;
        errorDiv.style.position = 'fixed';
        errorDiv.style.top = '20px';
        errorDiv.style.right = '20px';
        errorDiv.style.zIndex = '9999';
        
        document.body.appendChild(errorDiv);
        
        setTimeout(() => {
            if (errorDiv.parentNode) {
                errorDiv.parentNode.removeChild(errorDiv);
            }
        }, 5000);
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new Dashboard();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.dashboard) {
        window.dashboard.stopAutoRefresh();
    }
});