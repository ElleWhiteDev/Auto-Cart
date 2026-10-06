# Meal Plan Daily Summary Notifications

## Overview
This feature sends daily email summaries to all household members when meal plan changes occur. Instead of sending individual emails for each change, changes are batched and sent once per day.

## What's Included

### 1. Database Changes
- **New Table**: `meal_plan_changes` - Tracks all meal plan changes (additions, updates, deletions)
- **Migration Script**: `create_meal_plan_changes_table.py` - Run this once to create the table

### 2. Email Notifications
The system now tracks and emails:
- ✅ **Meals Added** - When a new meal is added to the plan
- ✏️ **Meals Updated** - When a meal is changed (future feature - currently only chef changes are tracked)
- ❌ **Meals Removed** - When a meal is deleted from the plan

### 3. Daily Summary Email
- Professional HTML email with Auto-Cart branding
- Groups changes by type (added/updated/deleted)
- Shows who made each change
- Includes link to view the meal plan
- Only sent if there are changes to report

## Setup Instructions

### Step 1: Run the Migration
```bash
python create_meal_plan_changes_table.py
```

### Step 2: Set Up Cron Job
The daily summaries are sent via a cron endpoint that should be called once per day.

#### Option A: Using cron (Linux/Mac)
Add this to your crontab (`crontab -e`):
```bash
# Send meal plan summaries at 8 PM every day
0 20 * * * curl -X POST -H "X-Cron-Token: YOUR_SECRET_TOKEN" https://your-domain.com/meal-plan/send-daily-summaries
```

#### Option B: Using a task scheduler service
Services like:
- **Heroku Scheduler** (if using Heroku)
- **AWS EventBridge** (if using AWS)
- **Google Cloud Scheduler** (if using GCP)
- **EasyCron** or **cron-job.org** (external services)

Configure them to POST to: `/meal-plan/send-daily-summaries`
With header: `X-Cron-Token: YOUR_SECRET_TOKEN`

### Step 3: Set Environment Variable
Add this to your environment variables:
```bash
CRON_SECRET_TOKEN=your-random-secret-token-here
```

Generate a secure random token:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## How It Works

### When Changes Occur
1. User adds/updates/deletes a meal in the meal plan
2. System creates a record in `meal_plan_changes` table with `emailed=False`
3. No immediate email is sent (except for chef removal notifications)

### Daily Summary Process
1. Cron job calls `/meal-plan/send-daily-summaries` endpoint
2. System finds all households with unemailed changes
3. For each household:
   - Collects all unemailed changes
   - Sends one summary email to all household members
   - Marks changes as `emailed=True`

## Testing

### Manual Test
You can manually trigger the daily summary:
```bash
curl -X POST \
  -H "X-Cron-Token: YOUR_SECRET_TOKEN" \
  http://localhost:5000/meal-plan/send-daily-summaries
```

### Test Flow
1. Add a meal to the meal plan
2. Delete a meal from the meal plan
3. Run the manual trigger command above
4. Check your email for the summary

## UI Changes

### Meal Type Dropdown
- Fixed placeholder text to not be selectable (added `disabled` attribute)
- Users must now select Breakfast, Lunch, or Dinner

## Future Enhancements

### Potential Additions
- Track meal recipe/name changes (not just additions/deletions)
- Track notes changes
- Track date/time changes
- Allow users to configure summary frequency (daily, weekly, instant)
- Allow users to opt-out of summaries
- Add summary preview in the web UI

## Troubleshooting

### Emails Not Sending
1. Check email configuration in environment variables:
   - `MAIL_USERNAME`
   - `MAIL_PASSWORD`
   - `MAIL_DEFAULT_SENDER`

2. Check application logs for errors:
   ```bash
   grep "meal plan summary" app.log
   ```

3. Verify cron job is running:
   ```bash
   grep CRON /var/log/syslog  # Linux
   log show --predicate 'process == "cron"' --last 1h  # Mac
   ```

### Changes Not Being Tracked
1. Verify the `meal_plan_changes` table exists:
   ```python
   from app import create_app
   from models import db, MealPlanChange
   app = create_app()
   with app.app_context():
       print(MealPlanChange.query.count())
   ```

2. Check if changes are being created:
   ```python
   with app.app_context():
       changes = MealPlanChange.query.filter_by(emailed=False).all()
       for c in changes:
           print(f"{c.change_type}: {c.meal_name} on {c.meal_date}")
   ```

## Security Notes

- The cron endpoint requires a secret token to prevent unauthorized access
- Keep your `CRON_SECRET_TOKEN` secure and don't commit it to version control
- The endpoint is not protected by login since it's meant to be called by automated systems
- Consider IP whitelisting if your cron service has a static IP

## Questions?

Contact the development team or check the application logs for more details.

