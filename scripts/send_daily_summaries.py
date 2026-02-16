#!/usr/bin/env python
"""
Script to send daily meal plan summaries.
This is designed to be run by Heroku Scheduler.
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def send_summaries():
    """Send daily meal plan summaries by calling the app endpoint"""
    
    # Get the app URL and cron token from environment
    app_url = os.environ.get('APP_URL', 'http://localhost:5000')
    cron_token = os.environ.get('CRON_SECRET_TOKEN')
    
    if not cron_token:
        print("ERROR: CRON_SECRET_TOKEN environment variable not set!")
        sys.exit(1)
    
    # Build the endpoint URL
    endpoint = f"{app_url.rstrip('/')}/meal-plan/send-daily-summaries"
    
    print(f"Sending daily meal plan summaries...")
    print(f"Endpoint: {endpoint}")
    
    try:
        # Make the POST request with the auth token
        response = requests.post(
            endpoint,
            headers={'X-Cron-Token': cron_token},
            timeout=60
        )
        
        # Check response
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Success! {result.get('message', 'Summaries sent')}")
            
            # Print details if available
            if 'results' in result:
                for r in result['results']:
                    status = r.get('status', 'unknown')
                    household_id = r.get('household_id', 'unknown')
                    if status == 'success':
                        print(f"  ✓ Household {household_id}: {status}")
                    else:
                        error = r.get('error', 'unknown error')
                        print(f"  ✗ Household {household_id}: {error}")
        else:
            print(f"✗ Error: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            sys.exit(1)
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Request failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    send_summaries()

