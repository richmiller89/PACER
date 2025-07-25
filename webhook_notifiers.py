#!/usr/bin/env python3
"""
Webhook notification handlers for various platforms
Extends the base PACER monitor with platform-specific formatting
"""

import json
import hmac
import hashlib
from datetime import datetime
from typing import Dict, List, Optional
import aiohttp
from abc import ABC, abstractmethod

class NotificationHandler(ABC):
    """Base class for notification handlers"""
    
    @abstractmethod
    async def send(self, case_data: Dict, new_entries: List[Dict]) -> bool:
        """Send notification for new case entries"""
        pass

class SlackNotifier(NotificationHandler):
    """Slack webhook notifications with rich formatting"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def send(self, case_data: Dict, new_entries: List[Dict]) -> bool:
        """Send formatted Slack notification"""
        
        # Build Slack blocks for rich formatting
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"⚖️ New Court Activity"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Case:*\n{case_data['case_number']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Court:*\n{case_data['court_id'].upper()}"
                    }
                ]
            }
        ]
        
        # Add case name if available
        if case_data.get('case_name'):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{case_data['case_name']}*"
                }
            })
        
        # Add new entries
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*New Entries ({len(new_entries)}):*"
            }
        })
        
        for entry in new_entries[:5]:  # Limit to 5 entries
            entry_text = f"• *Entry #{entry['entry_number']}* - {entry['date_filed']}\n"
            entry_text += f"  {entry['description'][:100]}..."
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": entry_text
                }
            })
        
        if len(new_entries) > 5:
            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": f"_... and {len(new_entries) - 5} more entries_"
                }]
            })
        
        # Add action buttons
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View on PACER"
                    },
                    "url": f"https://ecf.{case_data['court_id']}.uscourts.gov/cgi-bin/DktRpt.pl?{case_data['case_number']}"
                }
            ]
        })
        
        payload = {
            "blocks": blocks,
            "text": f"New activity in case {case_data['case_number']}"  # Fallback text
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.webhook_url, json=payload) as response:
                    return response.status == 200
            except Exception as e:
                logger.error(f"Slack notification failed: {e}")
                return False

class DiscordNotifier(NotificationHandler):
    """Discord webhook notifications with embeds"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def send(self, case_data: Dict, new_entries: List[Dict]) -> bool:
        """Send Discord embed notification"""
        
        # Create Discord embed
        embed = {
            "title": "⚖️ New Court Activity",
            "color": 0x0066CC,  # Blue color
            "fields": [
                {
                    "name": "Case Number",
                    "value": case_data['case_number'],
                    "inline": True
                },
                {
                    "name": "Court",
                    "value": case_data['court_id'].upper(),
                    "inline": True
                },
                {
                    "name": "New Entries",
                    "value": str(len(new_entries)),
                    "inline": True
                }
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Add case name if available
        if case_data.get('case_name'):
            embed["description"] = f"**{case_data['case_name']}**"
        
        # Add entry details
        entry_text = ""
        for i, entry in enumerate(new_entries[:5]):
            entry_text += f"**Entry #{entry['entry_number']}** - {entry['date_filed']}\n"
            entry_text += f"{entry['description'][:75]}...\n\n"
        
        if len(new_entries) > 5:
            entry_text += f"_... and {len(new_entries) - 5} more entries_"
        
        embed["fields"].append({
            "name": "Recent Activity",
            "value": entry_text or "No description available",
            "inline": False
        })
        
        payload = {
            "embeds": [embed],
            "username": "PACER Monitor",
            "avatar_url": "https://www.uscourts.gov/sites/default/files/styles/medium_3_2/public/pacer_0.jpg"
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{self.webhook_url}?wait=true", json=payload) as response:
                    return response.status in [200, 204]
            except Exception as e:
                logger.error(f"Discord notification failed: {e}")
                return False

class TeamsNotifier(NotificationHandler):
    """Microsoft Teams webhook notifications"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def send(self, case_data: Dict, new_entries: List[Dict]) -> bool:
        """Send Teams adaptive card notification"""
        
        # Create Teams adaptive card
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "0066CC",
            "summary": f"New activity in case {case_data['case_number']}",
            "sections": [
                {
                    "activityTitle": "⚖️ New Court Activity",
                    "activitySubtitle": case_data.get('case_name', 'Federal Court Case'),
                    "facts": [
                        {
                            "name": "Case Number:",
                            "value": case_data['case_number']
                        },
                        {
                            "name": "Court:",
                            "value": case_data['court_id'].upper()
                        },
                        {
                            "name": "New Entries:",
                            "value": str(len(new_entries))
                        }
                    ]
                }
            ]
        }
        
        # Add entry details
        entries_section = {
            "title": "Recent Docket Entries",
            "facts": []
        }
        
        for entry in new_entries[:3]:
            entries_section["facts"].append({
                "name": f"Entry #{entry['entry_number']}",
                "value": f"{entry['date_filed']} - {entry['description'][:50]}..."
            })
        
        card["sections"].append(entries_section)
        
        # Add action button
        card["potentialAction"] = [{
            "@type": "OpenUri",
            "name": "View on PACER",
            "targets": [{
                "os": "default",
                "uri": f"https://ecf.{case_data['court_id']}.uscourts.gov"
            }]
        }]
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.webhook_url, json=card) as response:
                    return response.status == 200
            except Exception as e:
                logger.error(f"Teams notification failed: {e}")
                return False

class GenericWebhookNotifier(NotificationHandler):
    """Generic webhook with HMAC signature verification"""
    
    def __init__(self, webhook_url: str, secret: Optional[str] = None):
        self.webhook_url = webhook_url
        self.secret = secret
    
    def generate_signature(self, payload: bytes) -> str:
        """Generate HMAC signature for payload"""
        if not self.secret:
            return ""
        
        return hmac.new(
            self.secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
    
    async def send(self, case_data: Dict, new_entries: List[Dict]) -> bool:
        """Send generic webhook notification"""
        
        payload = {
            "event": "case_update",
            "timestamp": datetime.utcnow().isoformat(),
            "case": {
                "number": case_data['case_number'],
                "court_id": case_data['court_id'],
                "name": case_data.get('case_name'),
                "url": f"https://ecf.{case_data['court_id']}.uscourts.gov"
            },
            "entries": [
                {
                    "number": entry['entry_number'],
                    "date_filed": entry['date_filed'],
                    "description": entry['description'],
                    "document_url": entry.get('document_url')
                }
                for entry in new_entries
            ],
            "summary": {
                "total_new_entries": len(new_entries),
                "latest_entry_date": max(e['date_filed'] for e in new_entries) if new_entries else None
            }
        }
        
        payload_bytes = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "PACER-Monitor/1.0"
        }
        
        if self.secret:
            headers["X-Signature"] = self.generate_signature(payload_bytes)
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self.webhook_url, 
                    data=payload_bytes, 
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    return response.status in [200, 201, 202, 204]
            except Exception as e:
                logger.error(f"Generic webhook notification failed: {e}")
                return False

class EmailNotifier(NotificationHandler):
    """Email notifications using SMTP"""
    
    def __init__(self, smtp_config: Dict):
        self.smtp_config = smtp_config
    
    async def send(self, case_data: Dict, new_entries: List[Dict]) -> bool:
        """Send email notification"""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # Create email content
        subject = f"PACER Alert: New activity in {case_data['case_number']}"
        
        # HTML email body
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>⚖️ New Court Activity</h2>
            
            <table style="margin: 20px 0;">
                <tr>
                    <td><strong>Case Number:</strong></td>
                    <td>{case_data['case_number']}</td>
                </tr>
                <tr>
                    <td><strong>Court:</strong></td>
                    <td>{case_data['court_id'].upper()}</td>
                </tr>
                <tr>
                    <td><strong>Case Name:</strong></td>
                    <td>{case_data.get('case_name', 'N/A')}</td>
                </tr>
            </table>
            
            <h3>New Docket Entries ({len(new_entries)})</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="background-color: #f0f0f0;">
                    <th style="padding: 8px; text-align: left;">Entry #</th>
                    <th style="padding: 8px; text-align: left;">Date Filed</th>
                    <th style="padding: 8px; text-align: left;">Description</th>
                </tr>
        """
        
        for entry in new_entries[:10]:
            html_body += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{entry['entry_number']}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{entry['date_filed']}</td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{entry['description']}</td>
                </tr>
            """
        
        html_body += """
            </table>
            
            <p style="margin-top: 20px;">
                <a href="https://ecf.{}.uscourts.gov" 
                   style="background-color: #0066CC; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                   View on PACER
                </a>
            </p>
            
            <hr style="margin-top: 30px;">
            <p style="font-size: 12px; color: #666;">
                This is an automated notification from PACER Monitor. 
                You are receiving this because you have notifications enabled for this case.
            </p>
        </body>
        </html>
        """.format(case_data['court_id'])
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.smtp_config['from_address']
        msg['To'] = ', '.join(self.smtp_config['to_addresses'])
        
        # Attach HTML part
        msg.attach(MIMEText(html_body, 'html'))
        
        # Send email
        try:
            with smtplib.SMTP(self.smtp_config['host'], self.smtp_config['port']) as server:
                server.starttls()
                server.login(self.smtp_config['username'], self.smtp_config['password'])
                server.send_message(msg)
            return True
        except Exception as e:
            logger.error(f"Email notification failed: {e}")
            return False

class NotificationManager:
    """Manages multiple notification handlers"""
    
    def __init__(self, config: Dict):
        self.handlers = []
        
        # Initialize handlers based on config
        if config.get('slack_webhook'):
            self.handlers.append(SlackNotifier(config['slack_webhook']))
        
        if config.get('discord_webhook'):
            self.handlers.append(DiscordNotifier(config['discord_webhook']))
        
        if config.get('teams_webhook'):
            self.handlers.append(TeamsNotifier(config['teams_webhook']))
        
        if config.get('generic_webhook'):
            self.handlers.append(GenericWebhookNotifier(
                config['generic_webhook'],
                config.get('webhook_secret')
            ))
        
        if config.get('email_enabled'):
            self.handlers.append(EmailNotifier(config['email']))
    
    async def notify_all(self, case_data: Dict, new_entries: List[Dict]):
        """Send notifications through all configured handlers"""
        results = []
        
        for handler in self.handlers:
            try:
                success = await handler.send(case_data, new_entries)
                results.append((handler.__class__.__name__, success))
            except Exception as e:
                logger.error(f"Handler {handler.__class__.__name__} failed: {e}")
                results.append((handler.__class__.__name__, False))
        
        return results

# Example usage
if __name__ == "__main__":
    import asyncio
    import logging
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Example configuration
    config = {
        "slack_webhook": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
        "discord_webhook": "https://discord.com/api/webhooks/YOUR/WEBHOOK",
        "email_enabled": True,
        "email": {
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "your-email@gmail.com",
            "password": "your-app-password",
            "from_address": "your-email@gmail.com",
            "to_addresses": ["recipient@example.com"]
        }
    }
    
    # Example case data
    case_data = {
        "case_number": "2:21-cv-00234",
        "court_id": "txed",
        "case_name": "Smith v. Jones"
    }
    
    new_entries = [
        {
            "entry_number": "45",
            "date_filed": "2024-01-15",
            "description": "ORDER granting Motion for Summary Judgment"
        },
        {
            "entry_number": "46",
            "date_filed": "2024-01-15",
            "description": "JUDGMENT entered in favor of Plaintiff"
        }
    ]
    
    # Send notifications
    async def test_notifications():
        manager = NotificationManager(config)
        results = await manager.notify_all(case_data, new_entries)
        
        for handler, success in results:
            print(f"{handler}: {'Success' if success else 'Failed'}")
    
    asyncio.run(test_notifications())