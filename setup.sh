#!/bin/bash
# PACER Monitor Setup Script
# This script sets up the PACER monitoring system

set -e

echo "==================================="
echo "PACER Case Monitor Setup"
echo "==================================="

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then 
    echo "Error: Python $required_version or higher is required (found $python_version)"
    exit 1
fi

echo "✓ Python version $python_version"

# Create virtual environment
echo -n "Creating virtual environment... "
python3 -m venv venv
source venv/bin/activate
echo "✓"

# Create requirements.txt
cat > requirements.txt << 'EOF'
# Core dependencies
requests>=2.28.0
redis>=4.5.0
sqlalchemy>=2.0.0
playwright>=1.30.0
asyncio>=3.4.3

# PACER and court data libraries
juriscraper>=2.5.0
courtlistener>=0.1.0

# Web automation
beautifulsoup4>=4.11.0
lxml>=4.9.0

# Utilities
python-dotenv>=0.21.0
pyyaml>=6.0
click>=8.1.0
rich>=13.0.0

# Notification support
aiohttp>=3.8.0
jinja2>=3.1.0

# Development tools
pytest>=7.2.0
pytest-asyncio>=0.20.0
black>=23.0.0
flake8>=6.0.0

# Database drivers (optional)
# psycopg2-binary>=2.9.0  # PostgreSQL
# pymysql>=1.0.0          # MySQL
EOF

# Install dependencies
echo -n "Installing Python dependencies... "
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1
echo "✓"

# Install Playwright browsers
echo -n "Installing Playwright browsers... "
playwright install chromium > /dev/null 2>&1
echo "✓"

# Create directory structure
echo -n "Creating directory structure... "
mkdir -p {logs,data,cache,config}
echo "✓"

# Create .env template
cat > .env.example << 'EOF'
# PACER Credentials
PACER_USERNAME=your_username
PACER_PASSWORD=your_password

# CourtListener API (optional but recommended)
COURTLISTENER_TOKEN=your_token

# Database URL (default: SQLite)
DATABASE_URL=sqlite:///data/pacer_monitor.db
# For PostgreSQL: postgresql://user:password@localhost/pacer_monitor

# Redis URL (optional)
REDIS_URL=redis://localhost:6379/0

# Webhook URL for notifications (optional)
WEBHOOK_URL=https://your-webhook-endpoint.com/pacer-updates

# Email notifications (optional)
EMAIL_NOTIFICATIONS=false
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EOF

# Create utility scripts
echo -n "Creating utility scripts... "

# Create add_cases.py
cat > add_cases.py << 'EOF'
#!/usr/bin/env python3
"""
Utility script to bulk add cases from CSV or interactive input
"""
import csv
import sys
from pacer_monitor import CaseMonitor, Config

def add_from_csv(filename):
    """Add cases from CSV file"""
    config = Config()
    monitor = CaseMonitor(config)
    
    with open(filename, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            monitor.add_case(
                case_number=row['case_number'],
                court_id=row['court_id'],
                priority=row.get('priority', 'medium')
            )
            print(f"Added: {row['case_number']} ({row['court_id']})")

def interactive_add():
    """Add cases interactively"""
    config = Config()
    monitor = CaseMonitor(config)
    
    print("\nAdd cases to monitor (Ctrl+C to finish)")
    print("Format: case_number,court_id,priority")
    print("Example: 2:21-cv-00234,txed,high\n")
    
    while True:
        try:
            entry = input("Enter case: ").strip()
            if not entry:
                continue
                
            parts = entry.split(',')
            if len(parts) < 2:
                print("Error: Need at least case_number and court_id")
                continue
                
            case_number = parts[0].strip()
            court_id = parts[1].strip()
            priority = parts[2].strip() if len(parts) > 2 else 'medium'
            
            monitor.add_case(case_number, court_id, priority)
            print(f"✓ Added {case_number}")
            
        except KeyboardInterrupt:
            print("\nFinished adding cases")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        add_from_csv(sys.argv[1])
    else:
        interactive_add()
EOF

chmod +x add_cases.py

# Create cost_report.py
cat > cost_report.py << 'EOF'
#!/usr/bin/env python3
"""
Generate cost reports and usage analytics
"""
from datetime import datetime, timedelta
from sqlalchemy import func
from pacer_monitor import CaseMonitor, Config, CostTracking
import rich
from rich.console import Console
from rich.table import Table

console = Console()

def generate_report():
    config = Config()
    monitor = CaseMonitor(config)
    
    # Current quarter costs
    current_cost = monitor.get_current_quarter_cost()
    remaining_budget = config.quarterly_budget - current_cost
    
    # Create summary table
    table = Table(title="PACER Cost Report")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Current Quarter", f"{datetime.now().year}-Q{(datetime.now().month-1)//3 + 1}")
    table.add_row("Total Spent", f"${current_cost:.2f}")
    table.add_row("Budget Remaining", f"${remaining_budget:.2f}")
    table.add_row("Budget Used", f"{(current_cost/config.quarterly_budget)*100:.1f}%")
    
    console.print(table)
    
    # Top cases by cost
    top_cases = monitor.db.query(
        CostTracking.case_number,
        func.sum(CostTracking.cost).label('total_cost'),
        func.count(CostTracking.id).label('query_count')
    ).group_by(
        CostTracking.case_number
    ).order_by(
        func.sum(CostTracking.cost).desc()
    ).limit(10).all()
    
    if top_cases:
        cost_table = Table(title="\nTop 10 Cases by Cost")
        cost_table.add_column("Case Number", style="cyan")
        cost_table.add_column("Total Cost", style="yellow")
        cost_table.add_column("Queries", style="green")
        
        for case in top_cases:
            cost_table.add_row(
                case.case_number,
                f"${case.total_cost:.2f}",
                str(case.query_count)
            )
        
        console.print(cost_table)
    
    # Cost projection
    days_in_quarter = 90
    current_day = (datetime.now() - datetime(datetime.now().year, ((datetime.now().month-1)//3)*3+1, 1)).days
    daily_rate = current_cost / max(current_day, 1)
    projected_cost = daily_rate * days_in_quarter
    
    console.print(f"\n[bold]Projections:[/bold]")
    console.print(f"Daily average: ${daily_rate:.2f}")
    console.print(f"Projected quarterly total: ${projected_cost:.2f}")
    
    if projected_cost > config.quarterly_budget:
        console.print(f"[red]⚠️  Warning: Current usage will exceed budget by ${projected_cost - config.quarterly_budget:.2f}[/red]")
    else:
        console.print(f"[green]✓ On track to stay within budget[/green]")

if __name__ == '__main__':
    generate_report()
EOF

chmod +x cost_report.py

# Create run.sh
cat > run.sh << 'EOF'
#!/bin/bash
# Run the PACER monitor

source venv/bin/activate

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check if config exists
if [ ! -f config/config.yaml ]; then
    echo "Error: config/config.yaml not found"
    echo "Copy config.yaml to config/ and customize it"
    exit 1
fi

# Run with proper Python path
PYTHONPATH=$PWD python3 pacer_monitor.py run
EOF

chmod +x run.sh

echo "✓"

# Create systemd service file (optional)
cat > pacer-monitor.service << 'EOF'
[Unit]
Description=PACER Case Monitor
After=network.target redis.service

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/path/to/pacer-monitor
Environment="PATH=/path/to/pacer-monitor/venv/bin"
ExecStart=/path/to/pacer-monitor/venv/bin/python pacer_monitor.py run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Final setup message
cat << 'EOF'

==================================="
Setup Complete!
==================================="

Next steps:

1. Copy and edit the configuration:
   cp config.yaml config/config.yaml
   # Edit config/config.yaml with your settings

2. Set up environment variables:
   cp .env.example .env
   # Edit .env with your credentials

3. Add cases to monitor:
   ./add_cases.py
   # Or import from CSV:
   ./add_cases.py cases.csv

4. Run the monitor:
   ./run.sh

5. Check costs anytime:
   ./cost_report.py

Optional: Install as a systemd service
   sudo cp pacer-monitor.service /etc/systemd/system/
   # Edit the service file with correct paths/user
   sudo systemctl enable pacer-monitor
   sudo systemctl start pacer-monitor

For development/testing:
   source venv/bin/activate
   python -m pytest tests/

Happy monitoring! Remember to stay under $30/quarter for free usage.
EOF