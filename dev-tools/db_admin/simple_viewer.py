#!/usr/bin/env python3
"""
Simple SQLite Database Web Viewer
A lightweight web interface without Flask-Admin dependencies
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, render_template_string, request, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)

def get_db_path():
    """Get database path from settings"""
    try:
        from database.connection import settings
        db_url = settings.database_url
        if db_url.startswith('sqlite:///'):
            return db_url[10:]
        return db_url
    except:
        return '../ai_agent_platform.db'

def get_db_connection():
    """Get SQLite connection"""
    db_path = get_db_path()
    if not os.path.exists(db_path):
        # Create empty database
        conn = sqlite3.connect(db_path)
        conn.close()
    return sqlite3.connect(db_path)

@app.route('/')
def dashboard():
    """Main dashboard"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    # Get table stats
    stats = {}
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            stats[table] = count
        except:
            stats[table] = "Error"
    
    # Get database info
    db_path = get_db_path()
    db_size = "N/A"
    if os.path.exists(db_path):
        db_size = f"{os.path.getsize(db_path) / 1024:.1f} KB"
    
    conn.close()
    
    return render_template_string(DASHBOARD_HTML, 
                                stats=stats, 
                                tables=tables,
                                db_path=db_path,
                                db_size=db_size,
                                current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

@app.route('/table/<table_name>')
def view_table(table_name):
    """View table data"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get column info
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    
    # Get data
    limit = request.args.get('limit', 50)
    cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
    rows = cursor.fetchall()
    
    conn.close()
    
    return render_template_string(TABLE_HTML,
                                table_name=table_name,
                                columns=columns,
                                rows=rows,
                                row_count=len(rows))

# HTML Templates
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>SQLite Database Viewer</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .card { background: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        .stat-card { background: #3498db; color: white; padding: 15px; border-radius: 5px; text-align: center; }
        .stat-number { font-size: 2em; font-weight: bold; }
        .stat-label { font-size: 0.9em; opacity: 0.9; }
        .table-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; }
        .table-link { display: block; padding: 15px; background: #34495e; color: white; text-decoration: none; border-radius: 5px; transition: background 0.3s; }
        .table-link:hover { background: #2c3e50; }
        .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .refresh-btn { background: #27ae60; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
        .refresh-btn:hover { background: #229954; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 SQLite Database Viewer</h1>
            <p>Real-time database monitoring and visualization</p>
        </div>
        
        <div class="info-grid">
            <div class="card">
                <h3>🗄️ Database Information</h3>
                <p><strong>Path:</strong> <code>{{ db_path }}</code></p>
                <p><strong>Size:</strong> {{ db_size }}</p>
                <p><strong>Last Updated:</strong> {{ current_time }}</p>
                <button class="refresh-btn" onclick="location.reload()">🔄 Refresh</button>
            </div>
            
            <div class="card">
                <h3>📈 Quick Stats</h3>
                <p><strong>Total Tables:</strong> {{ tables|length }}</p>
                <p><strong>Total Records:</strong> {{ stats.values()|sum if stats.values()|list|first != 'Error' else 'N/A' }}</p>
            </div>
        </div>
        
        <div class="card">
            <h3>📋 Table Statistics</h3>
            <div class="stats-grid">
                {% for table, count in stats.items() %}
                <div class="stat-card">
                    <div class="stat-number">{{ count }}</div>
                    <div class="stat-label">{{ table }}</div>
                </div>
                {% endfor %}
            </div>
        </div>
        
        <div class="card">
            <h3>🗂️ Browse Tables</h3>
            <div class="table-list">
                {% for table in tables %}
                <a href="/table/{{ table }}" class="table-link">
                    📋 {{ table }} ({{ stats[table] }} records)
                </a>
                {% endfor %}
            </div>
        </div>
    </div>
    
    <script>
        // Auto-refresh every 30 seconds
        setTimeout(() => location.reload(), 30000);
    </script>
</body>
</html>
'''

TABLE_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>{{ table_name }} - Database Viewer</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .card { background: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; border: 1px solid #ddd; text-align: left; }
        th { background: #34495e; color: white; }
        tr:nth-child(even) { background: #f9f9f9; }
        .back-btn { background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; margin-bottom: 20px; }
        .back-btn:hover { background: #2980b9; }
        .empty { text-align: center; color: #7f8c8d; padding: 40px; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back-btn">← Back to Dashboard</a>
        
        <div class="header">
            <h1>📋 {{ table_name }}</h1>
            <p>Showing {{ row_count }} records</p>
        </div>
        
        <div class="card">
            {% if rows %}
            <table>
                <thead>
                    <tr>
                        {% for column in columns %}
                        <th>{{ column }}</th>
                        {% endfor %}
                    </tr>
                </thead>
                <tbody>
                    {% for row in rows %}
                    <tr>
                        {% for cell in row %}
                        <td>{{ cell if cell is not none else 'NULL' }}</td>
                        {% endfor %}
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty">
                <h3>No data found</h3>
                <p>This table is empty or doesn't exist.</p>
            </div>
            {% endif %}
        </div>
    </div>
</body>
</html>
'''

if __name__ == '__main__':
    print("🚀 Starting Simple SQLite Database Viewer...")
    print("📊 Access at: http://localhost:5001")
    print("💡 Press Ctrl+C to stop")
    
    app.run(host='0.0.0.0', port=5001, debug=True) 