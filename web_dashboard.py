#!/usr/bin/env python3
"""
Web Dashboard for PACER Monitor
Provides a user-friendly interface for managing and monitoring cases
"""

from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from flask_cors import CORS
import json
from datetime import datetime, timedelta
from sqlalchemy import func
import plotly.graph_objs as go
import plotly.utils

# Import from main application
from pacer_monitor import CaseMonitor, Config, Case, CostTracking, DocketEntry

app = Flask(__name__)
CORS(app)

# Initialize monitor
config = Config()
monitor = CaseMonitor(config)

# HTML Template with embedded CSS and JavaScript
DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PACER Monitor Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #f5f5f5;
            color: #333;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            background-color: #0066cc;
            color: white;
            padding: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        h1 {
            font-size: 28px;
            font-weight: 600;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        
        .stat-card {
            background: white;
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        
        .stat-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }
        
        .stat-value {
            font-size: 36px;
            font-weight: bold;
            color: #0066cc;
            margin: 10px 0;
        }
        
        .stat-label {
            color: #666;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .warning {
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            color: #856404;
        }
        
        .success {
            background-color: #d4edda;
            border-left: 4px solid #28a745;
            color: #155724;
        }
        
        .section {
            background: white;
            padding: 30px;
            margin: 20px 0;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .section h2 {
            margin-bottom: 20px;
            color: #0066cc;
            font-size: 24px;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        
        th {
            background-color: #f8f9fa;
            font-weight: 600;
            color: #666;
        }
        
        tr:hover {
            background-color: #f8f9fa;
        }
        
        .priority-high {
            color: #dc3545;
            font-weight: bold;
        }
        
        .priority-medium {
            color: #ffc107;
        }
        
        .priority-low {
            color: #28a745;
        }
        
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: background-color 0.2s;
            text-decoration: none;
            display: inline-block;
        }
        
        .btn-primary {
            background-color: #0066cc;
            color: white;
        }
        
        .btn-primary:hover {
            background-color: #0052a3;
        }
        
        .btn-secondary {
            background-color: #6c757d;
            color: white;
        }
        
        .btn-small {
            padding: 5px 10px;
            font-size: 12px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: 500;
        }
        
        .form-group input, .form-group select {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
        }
        
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
        }
        
        .modal-content {
            background-color: white;
            margin: 15% auto;
            padding: 30px;
            border-radius: 8px;
            width: 500px;
            max-width: 90%;
        }
        
        .close {
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
        }
        
        .close:hover {
            color: black;
        }
        
        .chart-container {
            margin: 20px 0;
            height: 400px;
        }
        
        .badge {
            display: inline-block;
            padding: 4px 8px;
            font-size: 12px;
            border-radius: 12px;
            background-color: #e9ecef;
            color: #495057;
        }
        
        .footer {
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>⚖️ PACER Monitor Dashboard</h1>
        </div>
    </header>
    
    <div class="container">
        <!-- Stats Grid -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Active Cases</div>
                <div class="stat-value">{{ stats.total_cases }}</div>
            </div>
            
            <div class="stat-card {% if stats.budget_used > 25 %}warning{% else %}success{% endif %}">
                <div class="stat-label">Quarterly Budget Used</div>
                <div class="stat-value">${{ "%.2f"|format(stats.budget_used) }}</div>
                <small>${{ "%.2f"|format(30 - stats.budget_used) }} remaining</small>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Total Queries Today</div>
                <div class="stat-value">{{ stats.queries_today }}</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">New Entries (7 days)</div>
                <div class="stat-value">{{ stats.new_entries_week }}</div>
            </div>
        </div>
        
        <!-- Cost Chart -->
        <div class="section">
            <h2>Cost Tracking</h2>
            <div id="costChart" class="chart-container"></div>
        </div>
        
        <!-- Cases Table -->
        <div class="section">
            <h2>Monitored Cases 
                <button class="btn btn-primary btn-small" style="float: right;" onclick="showAddCaseModal()">
                    + Add Case
                </button>
            </h2>
            
            <table>
                <thead>
                    <tr>
                        <th>Case Number</th>
                        <th>Court</th>
                        <th>Name</th>
                        <th>Priority</th>
                        <th>Last Checked</th>
                        <th>Entries</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for case in cases %}
                    <tr>
                        <td><strong>{{ case.case_number }}</strong></td>
                        <td>{{ case.court_id|upper }}</td>
                        <td>{{ case.case_name or 'N/A' }}</td>
                        <td><span class="priority-{{ case.priority }}">{{ case.priority|title }}</span></td>
                        <td>
                            {% if case.last_checked %}
                                {{ case.last_checked.strftime('%Y-%m-%d %H:%M') }}
                            {% else %}
                                Never
                            {% endif %}
                        </td>
                        <td>{{ case.docket_entries_count }}</td>
                        <td>
                            <button class="btn btn-secondary btn-small" onclick="checkCase('{{ case.case_number }}')">
                                Check Now
                            </button>
                            <button class="btn btn-secondary btn-small" onclick="viewEntries('{{ case.case_number }}')">
                                View
                            </button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <!-- Recent Activity -->
        <div class="section">
            <h2>Recent Docket Entries</h2>
            <table>
                <thead>
                    <tr>
                        <th>Case</th>
                        <th>Entry #</th>
                        <th>Date Filed</th>
                        <th>Description</th>
                        <th>First Seen</th>
                    </tr>
                </thead>
                <tbody>
                    {% for entry in recent_entries %}
                    <tr>
                        <td>{{ entry.case_number }}</td>
                        <td>{{ entry.entry_number }}</td>
                        <td>{{ entry.date_filed.strftime('%Y-%m-%d') if entry.date_filed else 'N/A' }}</td>
                        <td>{{ entry.description[:100] }}{% if entry.description|length > 100 %}...{% endif %}</td>
                        <td>{{ entry.first_seen.strftime('%Y-%m-%d %H:%M') }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    
    <!-- Add Case Modal -->
    <div id="addCaseModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal()">&times;</span>
            <h2>Add New Case</h2>
            
            <form id="addCaseForm">
                <div class="form-group">
                    <label for="caseNumber">Case Number</label>
                    <input type="text" id="caseNumber" name="case_number" required 
                           placeholder="e.g., 2:21-cv-00234">
                </div>
                
                <div class="form-group">
                    <label for="courtId">Court ID</label>
                    <select id="courtId" name="court_id" required>
                        <option value="">Select Court</option>
                        <option value="nysd">S.D. New York</option>
                        <option value="cacd">C.D. California</option>
                        <option value="txed">E.D. Texas</option>
                        <option value="ilnd">N.D. Illinois</option>
                        <option value="flsd">S.D. Florida</option>
                        <option value="dcd">D. Columbia</option>
                        <!-- Add more courts as needed -->
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="priority">Priority</label>
                    <select id="priority" name="priority">
                        <option value="medium">Medium</option>
                        <option value="high">High</option>
                        <option value="low">Low</option>
                    </select>
                </div>
                
                <button type="submit" class="btn btn-primary">Add Case</button>
            </form>
        </div>
    </div>
    
    <footer class="footer">
        <p>PACER Monitor - Staying within the $30 quarterly free tier</p>
    </footer>
    
    <script>
        // Cost tracking chart
        var costData = {{ cost_chart_data|safe }};
        Plotly.newPlot('costChart', costData.data, costData.layout);
        
        // Modal functions
        function showAddCaseModal() {
            document.getElementById('addCaseModal').style.display = 'block';
        }
        
        function closeModal() {
            document.getElementById('addCaseModal').style.display = 'none';
        }
        
        // Add case form submission
        $('#addCaseForm').on('submit', function(e) {
            e.preventDefault();
            
            $.ajax({
                url: '/api/cases',
                method: 'POST',
                data: $(this).serialize(),
                success: function(response) {
                    alert('Case added successfully!');
                    closeModal();
                    location.reload();
                },
                error: function(xhr) {
                    alert('Error: ' + xhr.responseJSON.error);
                }
            });
        });
        
        // Check case now
        function checkCase(caseNumber) {
            if (confirm('Check this case now? This will use your PACER budget.')) {
                $.ajax({
                    url: '/api/cases/' + caseNumber + '/check',
                    method: 'POST',
                    success: function(response) {
                        alert('Case check initiated. Refresh in a moment to see results.');
                    },
                    error: function(xhr) {
                        alert('Error: ' + xhr.responseJSON.error);
                    }
                });
            }
        }
        
        // View case entries
        function viewEntries(caseNumber) {
            window.location.href = '/cases/' + caseNumber;
        }
        
        // Auto-refresh every 60 seconds
        setTimeout(function() {
            location.reload();
        }, 60000);
        
        // Close modal when clicking outside
        window.onclick = function(event) {
            if (event.target.className === 'modal') {
                event.target.style.display = 'none';
            }
        }
    </script>
</body>
</html>
'''

@app.route('/')
def dashboard():
    """Main dashboard view"""
    # Get statistics
    stats = {
        'total_cases': monitor.db.query(Case).count(),
        'budget_used': monitor.get_current_quarter_cost(),
        'queries_today': monitor.db.query(CostTracking).filter(
            CostTracking.date >= datetime.utcnow().date()
        ).count(),
        'new_entries_week': monitor.db.query(DocketEntry).filter(
            DocketEntry.first_seen >= datetime.utcnow() - timedelta(days=7)
        ).count()
    }
    
    # Get all cases
    cases = monitor.db.query(Case).order_by(Case.priority.desc()).all()
    
    # Get recent entries
    recent_entries = monitor.db.query(DocketEntry).order_by(
        DocketEntry.first_seen.desc()
    ).limit(10).all()
    
    # Generate cost chart data
    cost_chart_data = generate_cost_chart()
    
    return render_template_string(
        DASHBOARD_TEMPLATE,
        stats=stats,
        cases=cases,
        recent_entries=recent_entries,
        cost_chart_data=json.dumps(cost_chart_data)
    )

@app.route('/api/cases', methods=['POST'])
def add_case():
    """API endpoint to add a new case"""
    try:
        case_number = request.form.get('case_number')
        court_id = request.form.get('court_id')
        priority = request.form.get('priority', 'medium')
        
        if not case_number or not court_id:
            return jsonify({'error': 'Case number and court ID required'}), 400
        
        monitor.add_case(case_number, court_id, priority)
        
        return jsonify({'success': True, 'message': 'Case added successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cases/<case_number>/check', methods=['POST'])
def check_case_now(case_number):
    """Force check a specific case"""
    try:
        case = monitor.db.query(Case).filter_by(case_number=case_number).first()
        if not case:
            return jsonify({'error': 'Case not found'}), 404
        
        # Reset last checked to force immediate check
        case.last_checked = None
        monitor.db.commit()
        
        # In production, this would trigger the monitoring task
        # For now, we'll just return success
        return jsonify({'success': True, 'message': 'Case check initiated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats/costs')
def cost_stats():
    """API endpoint for cost statistics"""
    try:
        # Get daily costs for the current quarter
        now = datetime.utcnow()
        quarter_start = datetime(now.year, ((now.month-1)//3)*3+1, 1)
        
        daily_costs = monitor.db.query(
            func.date(CostTracking.date).label('date'),
            func.sum(CostTracking.cost).label('total_cost')
        ).filter(
            CostTracking.date >= quarter_start
        ).group_by(
            func.date(CostTracking.date)
        ).all()
        
        return jsonify({
            'daily_costs': [
                {
                    'date': cost.date.strftime('%Y-%m-%d'),
                    'cost': float(cost.total_cost)
                }
                for cost in daily_costs
            ],
            'total_quarter_cost': monitor.get_current_quarter_cost(),
            'budget_remaining': config.quarterly_budget - monitor.get_current_quarter_cost()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_cost_chart():
    """Generate Plotly chart data for cost tracking"""
    # Get daily costs for current quarter
    now = datetime.utcnow()
    quarter_start = datetime(now.year, ((now.month-1)//3)*3+1, 1)
    
    daily_costs = monitor.db.query(
        func.date(CostTracking.date).label('date'),
        func.sum(CostTracking.cost).label('cost')
    ).filter(
        CostTracking.date >= quarter_start
    ).group_by(
        func.date(CostTracking.date)
    ).order_by('date').all()
    
    # Calculate cumulative costs
    dates = []
    cumulative_costs = []
    running_total = 0
    
    for record in daily_costs:
        dates.append(record.date.strftime('%Y-%m-%d'))
        running_total += float(record.cost)
        cumulative_costs.append(running_total)
    
    # Create Plotly trace
    trace = go.Scatter(
        x=dates,
        y=cumulative_costs,
        mode='lines+markers',
        name='Cumulative Cost',
        line=dict(color='#0066cc', width=2),
        marker=dict(size=6)
    )
    
    # Add budget line
    budget_line = go.Scatter(
        x=[dates[0] if dates else quarter_start.strftime('%Y-%m-%d'), 
           (quarter_start + timedelta(days=90)).strftime('%Y-%m-%d')],
        y=[30, 30],
        mode='lines',
        name='Budget Limit ($30)',
        line=dict(color='red', width=2, dash='dash')
    )
    
    layout = go.Layout(
        title='Quarterly Cost Tracking',
        xaxis=dict(title='Date'),
        yaxis=dict(title='Cost ($)', rangemode='tozero'),
        hovermode='x unified',
        showlegend=True
    )
    
    return {
        'data': [trace, budget_line],
        'layout': layout
    }

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)