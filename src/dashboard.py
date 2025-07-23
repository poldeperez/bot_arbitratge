# filepath: /Users/poldeperezcabrero/Projects/bot_arbitratge/src/dashboard.py
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, flash
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import os
import time
import json
from datetime import datetime, timedelta
import re
import redis
from collections import defaultdict
import docker
from dotenv import load_dotenv

# Configurar paths correctos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# Cargar .env desde la raíz del proyecto
env_path = os.path.join(PROJECT_ROOT, 'venv', '.env')
load_dotenv(env_path)

# Configurar Flask con paths correctos
template_dir = os.path.join(BASE_DIR, 'templates')
static_dir = os.path.join(BASE_DIR, 'static')
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Configuración de usuarios
USERS = {
    'admin': generate_password_hash(os.getenv('ADMIN_PASSWORD')),
    'viewer': generate_password_hash(os.getenv('VIEWER_PASSWORD'))
}

# Roles de usuarios
USER_ROLES = {
    'admin': ['admin', 'viewer'],
    'viewer': ['viewer']
}

class DashboardManager:
    def __init__(self):
        # Detectar si estamos en Docker o desarrollo local
        if os.path.exists("/app/logs"):  # Docker environment
            self.logs_path = "/app/logs"
        else:  # Local development
            self.logs_path = os.path.join(PROJECT_ROOT, 'logs')
        # Crear directorio de logs si no existe
        os.makedirs(self.logs_path, exist_ok=True)

        self.active_symbols = [s.strip().upper() for s in os.getenv("DASHBOARD_SYMBOLS", "BTC,ETH").split(',') if s.strip()]
        
        self.redis_client = None
        self._setup_redis()

        # Configurar Docker client
        self.docker_client = None
        try:
            self.docker_client = docker.from_env()
            print(f"Docker client connected successfully")
        except Exception as e:
            print(f"Warning: Could not connect to Docker: {e}")
            print(f"Dashboard will work in read-only mode")
    
    def _setup_redis(self):
        """Configura conexión Redis con fallback"""
        try:
            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            
            # Test connection
            self.redis_client.ping()
            print(f"Dashboard Redis connected successfully")
            
        except Exception as e:
            print(f"Dashboard Redis connection failed: {e}")
            print(f"Will use JSON files as fallback")
            self.redis_client = None

    def get_log_files(self):
        """Obtiene lista de archivos de log"""
        try:
            if os.path.exists(self.logs_path):
                files = [f for f in os.listdir(self.logs_path) if f.endswith('.log')]
                return sorted(files)
            else:
                print(f"Logs directory not found: {self.logs_path}")
                return []
        except Exception as e:
            print(f"Error reading logs directory: {e}")
            return []
    
    def read_recent_logs(self, filename, lines=200):
        """Lee las últimas N líneas de un archivo de log"""
        try:
            # Validar filename por seguridad
            if not re.match(r'^[\w\-_.]+\.log$', filename):
                return ["Invalid filename"]
            
            filepath = os.path.join(self.logs_path, filename)
            if not os.path.exists(filepath):
                return [f"Log file not found: {filepath}"]
            
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                return all_lines[-lines:] if len(all_lines) > lines else all_lines
        except Exception as e:
            return [f"Error reading log file: {e}"]
    
    # ...resto del código igual...
    def get_error_summary(self):
        """Resume errores por exchange y crypto"""
        error_count = defaultdict(int)
        recent_errors = []
        
        for log_file in self.get_log_files():
            lines = self.read_recent_logs(log_file, 500)
            for line in lines:
                if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}.*ERROR', line):
                    # Extraer crypto del nombre del archivo
                    crypto = "Unknown"
                    if "btc" in log_file.lower():
                        crypto = "BTC"
                    elif "eth" in log_file.lower():
                        crypto = "ETH"
                    
                    # Extraer exchange del contenido o nombre de archivo
                    exchange = "Unknown"
                    line_lower = line.lower()
                    if "live_price_adv_cb_ws" in line_lower:
                        exchange = "Coinbase"
                    elif "live_price_binance_ws" in line_lower:
                        exchange = "Binance"
                    elif "live_price_bybit_ws" in line_lower:
                        exchange = "Bybit"
                    elif "live_price_kucoin_ws" in line_lower:
                        exchange = "Kucoin"
                    
                    key = f"{crypto}-{exchange}"
                    error_count[key] += 1
                    
                    if len(recent_errors) < 50:
                        recent_errors.append({
                            'timestamp': self.extract_timestamp(line),
                            'crypto': crypto,
                            'exchange': exchange,
                            'message': line.strip()[:200]
                        })
        
        return dict(error_count), recent_errors[-20:]
    
    def extract_timestamp(self, log_line):
        """Extrae timestamp de una línea de log"""
        match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', log_line)
        return match.group(1) if match else "Unknown"
    
    def get_exchange_status_from_redis(self):
        """Lee estado de exchanges desde Redis"""
        if not self.redis_client:
            return None
            
        status = {}
        
        try:
            for symbol in self.active_symbols:
                key = f"status:{symbol}"
                data_json = self.redis_client.get(key)
                
                if data_json:
                    data = json.loads(data_json)
                    status[symbol] = {
                        'status': 'active',
                        'last_update': data.get('last_update', 0),
                        'last_update_readable': data.get('last_update_readable', 'Unknown'),
                        'exchanges': data.get('exchanges', {}),
                        'source': 'redis'
                    }
                else:
                    # No data in Redis = bot offline or Redis issue
                    status[symbol] = {
                        'status': 'no_data',
                        'last_update': 0,
                        'exchanges': {},
                        'source': 'redis'
                    }
            
            return status
            
        except Exception as e:
            print(f"Error reading from Redis: {e}")
            return None
    
    def get_exchange_status_from_files(self):
        """Lee estado de exchanges desde archivos JSON generados por los bots"""
        status = {}

        for symbol in self.active_symbols:
            status_file = os.path.join(self.logs_path, f'status_{symbol}.json')
            
            try:
                if os.path.exists(status_file):
                    # Verificar que el archivo no sea muy viejo (bot activo)
                    file_age = time.time() - os.path.getmtime(status_file)
                    
                    if file_age > 60:  # Más de 60 segundos = bot probablemente caído
                        status[symbol] = {
                            'status': 'stale',
                            'last_update': file_age,
                            'exchanges': {},
                            'source': 'json_file'
                        }
                        continue
                    
                    with open(status_file, 'r') as f:
                        data = json.load(f)
                        
                    status[symbol] = {
                        'status': 'active',
                        'last_update': data.get('last_update', 0),
                        'last_update_readable': data.get('last_update_readable', 'Unknown'),
                        'exchanges': data.get('exchanges', {}),
                        'source': 'json_file'
                    }
                else:
                    status[symbol] = {
                        'status': 'no_data',
                        'last_update': 0,
                        'exchanges': {},
                        'source': 'json_file'
                    }
                    
            except Exception as e:
                print(f"Error reading status file {status_file}: {e}")
                status[symbol] = {
                    'status': 'error',
                    'error': str(e),
                    'exchanges': {},
                    'source': 'json_file'
                }
        
        return status
    
    def get_exchange_status_hybrid(self):
        """Obtiene estado con Redis como primario y JSON como fallback"""
        # Intentar Redis primero
        redis_status = self.get_exchange_status_from_redis()
        if redis_status:
            return redis_status
        
        # Fallback a archivos JSON
        print("Redis not available, using JSON files")
        return self.get_exchange_status_from_files()
    
    def get_exchange_status(self):
        """Estado de exchanges basado en Redis/JSON híbrido"""
        status = {}
        file_status = self.get_exchange_status_hybrid()
        
        for symbol, data in file_status.items():
            for exchange, exchange_data in data.get('exchanges', {}).items():
                key = f"{symbol}-{exchange}"
                
                if data['status'] == 'active':
                    # Verificar si el exchange específico está conectado
                    exchange_status = exchange_data.get('status', 'unknown')
                    
                    # Verificar si los datos son recientes
                    if exchange_data.get('timestamp'):
                        age = time.time() - exchange_data['timestamp']
                        if age > 60:
                            exchange_status = 'stale'
                    
                    status[key] = exchange_status
                else:
                    status[key] = data['status']
        
        return status

    def get_opportunities_from_logs(self):
        """Extrae oportunidades de arbitraje desde logs arb_op_*"""
        opportunities = {}
        recent_opportunities = []
        
        # Buscar archivos de oportunidades
        op_files = [f for f in self.get_log_files() if f.startswith('arb_op_') and f.endswith('.log')]
        
        # Regex para parsear líneas de oportunidades
        opportunity_pattern = re.compile(
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?'  # Timestamp
            r'(\w+) Arbitrage opportunity! '                     # Symbol
            r'Profit: ([\d.]+) USDT.*?'                        # Profit
            r'Buy on (\w+) at ([\d.]+).*?'                     # Buy exchange + price
            r'Sell on (\w+) at ([\d.]+)'                       # Sell exchange + price
        )
        
        for op_file in op_files:
            try:
                lines = self.read_recent_logs(op_file, 1000)  # Últimas 1000 líneas
                
                for line in lines:
                    if 'Arbitrage opportunity!' in line:
                        match = opportunity_pattern.search(line)
                        if match:
                            timestamp_str, symbol, profit, buy_exchange, buy_price, sell_exchange, sell_price = match.groups()
                            
                            # Parsear timestamp
                            try:
                                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                                
                                # Solo contar oportunidades de las últimas 24 horas
                                if timestamp > datetime.now() - timedelta(hours=24):
                                    # Contar por símbolo
                                    if symbol not in opportunities:
                                        opportunities[symbol] = {
                                            'count': 0,
                                            'total_profit': 0.0,
                                            'best_profit': 0.0
                                        }
                                    
                                    profit_float = float(profit)
                                    opportunities[symbol]['count'] += 1
                                    opportunities[symbol]['total_profit'] += profit_float
                                    opportunities[symbol]['best_profit'] = max(
                                        opportunities[symbol]['best_profit'], 
                                        profit_float
                                    )
                                    
                                    # Agregar a recientes (últimas 10)
                                    if len(recent_opportunities) < 50:
                                        recent_opportunities.append({
                                            'timestamp': timestamp_str,
                                            'symbol': symbol,
                                            'profit': profit_float,
                                            'buy_exchange': buy_exchange,
                                            'buy_price': float(buy_price),
                                            'sell_exchange': sell_exchange,
                                            'sell_price': float(sell_price),
                                            'spread_pct': round(((float(sell_price) - float(buy_price)) / float(buy_price)) * 100, 4)
                                        })
                                        
                            except ValueError as e:
                                print(f"Error parsing opportunity timestamp: {e}")
                                continue
                                
            except Exception as e:
                print(f"Error reading opportunity log {op_file}: {e}")
                continue
        
        # Ordenar recientes por timestamp (más nuevo primero)
        recent_opportunities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return opportunities, recent_opportunities[:10]  # Solo últimas 10
    
    def get_opportunities_summary(self):
        """Resumen de oportunidades para la API"""
        opportunities, recent = self.get_opportunities_from_logs()
        
        # Calcular totales
        total_opportunities = sum(data['count'] for data in opportunities.values())
        total_profit = sum(data['total_profit'] for data in opportunities.values())
        
        return {
            'by_symbol': opportunities,
            'recent_opportunities': recent,
            'total_count': total_opportunities,
            'total_profit': round(total_profit, 2),
            'symbols_active': len(opportunities)
        }
    
    def get_docker_containers(self):
        """Obtiene información de contenedores Docker"""
        if not self.docker_client:
            return []
        
        try:
            containers = []
            for container in self.docker_client.containers.list(all=True):
                containers.append({
                    'id': container.id[:12],
                    'name': container.name,
                    'status': container.status,
                    'image': container.image.tags[0] if container.image.tags else 'unknown',
                    'created': container.attrs['Created'],
                })
            return containers
        except Exception as e:
            print(f"Error getting Docker containers: {e}")
            return []

# Decoradores de autenticación
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session or 'admin' not in USER_ROLES.get(session['user'], []):
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('dashboard_home'))
        return f(*args, **kwargs)
    return decorated_function

# Instancia del manager
dashboard = DashboardManager()

# Rutas de autenticación
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username in USERS and check_password_hash(USERS[username], password):
            session['user'] = username
            flash(f'Welcome, {username}!', 'success')
            return redirect(url_for('dashboard_home'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

# Rutas principales
@app.route('/')
@login_required
def dashboard_home():
    return render_template('dashboard.html', user=session.get('user'))

@app.route('/containers')
@admin_required
def containers():
    return render_template('containers.html', user=session.get('user'))

# APIs
@app.route('/api/status')
@login_required
def api_status():
    error_count, recent_errors = dashboard.get_error_summary()
    exchange_status = dashboard.get_exchange_status()
    file_status = dashboard.get_exchange_status_hybrid()
    opportunities_data = dashboard.get_opportunities_summary()
    return jsonify({
        'exchanges': exchange_status,
        'file_status': file_status,
        'error_count': error_count,
        'recent_errors': recent_errors,
        'opportunities': opportunities_data,
        'redis_available': dashboard.redis_client is not None,
        'timestamp': datetime.now().isoformat(),
        'user': session.get('user'),
        'logs_path': dashboard.logs_path  # Para debugging
    })

@app.route('/api/logs/<filename>')
@login_required
def api_logs(filename):
    lines = dashboard.read_recent_logs(filename, 200)
    return jsonify({
        'filename': filename,
        'lines': lines,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/logs')
@login_required
def api_logs_list():
    return jsonify({
        'files': dashboard.get_log_files(),
        'logs_path': dashboard.logs_path  # Para debugging
    })

@app.route('/api/opportunities')
@login_required
def api_opportunities():
    """Endpoint para obtener datos de oportunidades de arbitraje"""
    try:
        opportunities_data = dashboard.get_opportunities_summary()
        return jsonify({
            'success': True,
            'data': opportunities_data,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        })

@app.route('/api/containers')
@admin_required
def api_containers():
    return jsonify({
        'containers': dashboard.get_docker_containers(),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/containers/<container_id>/restart', methods=['POST'])
@admin_required
def api_container_restart(container_id):
    if not dashboard.docker_client:
        return jsonify({'error': 'Docker not available'}), 500
    
    try:
        container = dashboard.docker_client.containers.get(container_id)
        container.restart()
        return jsonify({'success': True, 'message': f'Container {container_id} restarted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Raw status API
@app.route('/api/raw-status')
@login_required
def api_raw_status():
    """Endpoint para ver los archivos de status en crudo"""
    return jsonify({
        'file_status': dashboard.get_exchange_status_from_files(),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/redis-status')
@login_required
def api_redis_status():
    """Endpoint para ver estado de Redis"""
    if not dashboard.redis_client:
        return jsonify({'redis_available': False, 'error': 'Redis not connected'})
    
    try:
        info = dashboard.redis_client.info()
        keys = dashboard.redis_client.keys('status:*')
        
        return jsonify({
            'redis_available': True,
            'redis_info': {
                'version': info.get('redis_version'),
                'connected_clients': info.get('connected_clients'),
                'used_memory_human': info.get('used_memory_human'),
                'uptime_in_seconds': info.get('uptime_in_seconds')
            },
            'active_keys': keys,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'redis_available': False, 'error': str(e)})
    
# Debug route para verificar paths
@app.route('/debug/paths')
def debug_paths():
    if app.debug:
        return jsonify({
            'BASE_DIR': BASE_DIR,
            'PROJECT_ROOT': PROJECT_ROOT,
            'env_path': env_path,
            'template_dir': template_dir,
            'static_dir': static_dir,
            'logs_path': dashboard.logs_path,
            'env_file_exists': os.path.exists(env_path),
            'templates_exist': os.path.exists(template_dir),
            'static_exists': os.path.exists(static_dir),
            'logs_exist': os.path.exists(dashboard.logs_path)
        })
    return "Debug mode disabled"

if __name__ == '__main__':
    print(f"Starting dashboard...")
    print(f"Base directory: {BASE_DIR}")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Logs path: {dashboard.logs_path}")
    print(f"Templates path: {template_dir}")
    print(f"Static path: {static_dir}")
    
    app.run(host='0.0.0.0', port=5001, debug=True)