# PACER Case Monitor

A cost-optimized federal court case monitoring system that tracks up to 20-30 cases while staying within PACER's $30 quarterly free tier. Uses open-source libraries and intelligent caching to minimize costs.

## Features

- **Cost Optimization**: Stays within $30/quarter free tier with intelligent query management
- **Multi-Source Data**: Checks free CourtListener/RECAP data before querying PACER
- **Smart Polling**: Adaptive intervals based on case priority (high/medium/low)
- **Real-time Notifications**: Webhook, email, and extensible notification system
- **Compliance**: Follows PACER terms of service and recommended polling hours
- **Caching**: Redis-based caching to minimize redundant queries
- **Browser Automation**: Playwright-based scraping for complex court interfaces

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/pacer-monitor
cd pacer-monitor

# Run the setup script
chmod +x setup.sh
./setup.sh
```

### 2. Configuration

```bash
# Copy and edit the configuration file
cp config.yaml config/config.yaml
nano config/config.yaml

# Set up environment variables
cp .env.example .env
nano .env
```

Required settings:
- PACER username and password
- CourtListener API token (recommended for free data)
- Notification endpoints (webhook URL, email settings)

### 3. Add Cases to Monitor

Interactive mode:
```bash
./add_cases.py
```

Or import from CSV:
```bash
# Create a CSV file with columns: case_number,court_id,priority
./add_cases.py cases.csv
```

### 4. Run the Monitor

```bash
./run.sh
```

## Usage Examples

### Adding Cases

```python
# Via command line
python pacer_monitor.py add --case-number "2:21-cv-00234" --court-id "txed" --priority high

# Via Python API
from pacer_monitor import CaseMonitor, Config

monitor = CaseMonitor(Config())
monitor.add_case("1:20-cv-05678", "nysd", priority="medium")
```

### Checking Costs

```bash
# Generate cost report
./cost_report.py

# Via command line
python pacer_monitor.py costs
```

### Court ID Reference

Common federal courts:
- `nysd` - Southern District of New York
- `cacd` - Central District of California  
- `txed` - Eastern District of Texas
- `dcd` - District of Columbia
- `ca9` - Ninth Circuit Court of Appeals

Full list: https://www.pacer.gov/psco/cgi-bin/links.pl

## Cost Management

The system implements several strategies to stay within the $30 quarterly free tier:

1. **Free Data First**: Always checks CourtListener/RECAP before PACER
2. **Smart Polling**: 
   - High priority: Every hour
   - Medium priority: Every 6 hours
   - Low priority: Every 24 hours
3. **Cost Tracking**: Real-time monitoring with safety buffer
4. **Off-Peak Hours**: Queries between 6 PM - 6 AM Central Time

### Cost Calculations

- PACER charges $0.10 per page (max $3.00 per document)
- Quarterly allowance: ~300 free pages
- Recommended distribution:
  - 10 high-priority cases: ~150 pages/quarter
  - 10 medium-priority cases: ~100 pages/quarter
  - 10 low-priority cases: ~50 pages/quarter

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   CLI/Web UI    │     │ Notification    │     │   Cost Tracker  │
└────────┬────────┘     │    Service      │     └────────┬────────┘
         │              └────────┬────────┘              │
         │                       │                        │
┌────────▼──────────────────────▼────────────────────────▼────────┐
│                        Case Monitor Core                         │
│  • Priority-based polling                                        │
│  • Cost optimization                                             │
│  • Change detection                                              │
└────────┬──────────────────────┬────────────────────────┬────────┘
         │                      │                         │
┌────────▼────────┐    ┌────────▼────────┐     ┌────────▼────────┐
│  CourtListener  │    │     PACER       │     │   Redis Cache   │
│   (Free API)    │    │  (Web Scraper)  │     │                 │
└─────────────────┘    └─────────────────┘     └─────────────────┘
```

## Advanced Configuration

### Database Options

SQLite (default, good for up to 30 cases):
```yaml
database:
  url: "sqlite:///data/pacer_monitor.db"
```

PostgreSQL (for production/scale):
```yaml
database:
  url: "postgresql://user:password@localhost/pacer_monitor"
```

### Notification Filters

```yaml
notifications:
  filters:
    document_types:
      - "ORDER"
      - "OPINION"
      - "JUDGMENT"
    rate_limit: 3600  # Max 1 notification per hour per case
```

### Custom Priority Rules

```yaml
priority_rules:
  high:
    keywords:
      - "preliminary injunction"
      - "emergency"
  low:
    keywords:
      - "stayed"
      - "closed"
```

## Development

### Running Tests

```bash
source venv/bin/activate
python -m pytest tests/
```

### Code Style

```bash
# Format code
black .

# Check style
flake8 .
```

### Adding New Features

1. Notification providers: Implement `NotificationProvider` interface
2. Court scrapers: Extend `CourtScraper` base class
3. Cost strategies: Add to `CostOptimizer` class

## Deployment

### Systemd Service

```bash
# Copy and edit service file
sudo cp pacer-monitor.service /etc/systemd/system/
sudo nano /etc/systemd/system/pacer-monitor.service

# Enable and start
sudo systemctl enable pacer-monitor
sudo systemctl start pacer-monitor
```

### Docker

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN playwright install chromium

COPY . .
CMD ["python", "pacer_monitor.py", "run"]
```

## Legal Compliance

This system is designed to comply with PACER terms of service:

- ✅ Respects rate limits and polling hours
- ✅ Pays all applicable fees
- ✅ No circumvention of access controls
- ✅ Uses official APIs where available

**Important**: Always consult with legal counsel before deploying any court data scraping system.

## Troubleshooting

### Common Issues

1. **"Approaching budget limit" warnings**
   - Reduce polling frequency
   - Prioritize fewer cases as "high"
   - Enable more aggressive caching

2. **Login failures**
   - Verify PACER credentials
   - Check if account is in good standing
   - Ensure IP isn't blocked

3. **Missing notifications**
   - Verify webhook URL is accessible
   - Check notification filters
   - Review logs for errors

### Debug Mode

```bash
# Run with debug logging
LOG_LEVEL=DEBUG ./run.sh

# Test specific case
python pacer_monitor.py test --case-number "2:21-cv-00234"
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - See LICENSE file for details

## Disclaimer

This software is provided for educational and lawful purposes only. Users are responsible for ensuring their use complies with all applicable laws and PACER terms of service. The authors assume no liability for misuse.

## Support

- Issues: GitHub Issues
- Documentation: Wiki
- Community: Discussions

Remember: Stay under $30/quarter to avoid fees!