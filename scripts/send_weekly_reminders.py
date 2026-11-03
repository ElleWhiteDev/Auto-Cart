#!/usr/bin/env python
"""
Script to send the weekly "plan your meals" reminder emails.
This is designed to be run hourly by Heroku Scheduler; the app only sends
the emails during the Sunday 7pm Eastern hour, so DST is handled for us.

Pass --force to send immediately regardless of the day/time (for testing).
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def send_reminders(force=False):
    """Send weekly meal plan reminders by calling the app endpoint"""

    # Get the app URL and cron token from environment
    app_url = os.environ.get('APP_URL', 'http://localhost:5000')
    cron_token = os.environ.get('CRON_SECRET_TOKEN')

    if not cron_token:
        print("ERROR: CRON_SECRET_TOKEN environment variable not set!")
        sys.exit(1)

    # Build the endpoint URL
    endpoint = f"{app_url.rstrip('/')}/meal-plan/send-weekly-reminders"

    print(f"Sending weekly meal plan reminders...")
    print(f"Endpoint: {endpoint}")

    try:
        response = requests.post(
            endpoint,
            headers={'X-Cron-Token': cron_token},
            data={'force': '1'} if force else None,
            timeout=120
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✓ {result.get('message', 'Done')}")
            if 'emails_sent' in result:
                print(f"  Sent: {result['emails_sent']}, failed: {result.get('emails_failed', 0)}")
        else:
            print(f"✗ Error: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            sys.exit(1)

    except requests.exceptions.RequestException as e:
        print(f"✗ Request failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    send_reminders(force='--force' in sys.argv)
