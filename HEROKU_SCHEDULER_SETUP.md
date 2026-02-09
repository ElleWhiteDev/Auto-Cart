# Heroku Scheduler Setup for Daily Meal Plan Summaries

## Prerequisites
- Heroku app already deployed
- Heroku CLI installed (optional, but helpful)

## Step 1: Add Heroku Scheduler Add-on

### Via Heroku Dashboard:
1. Go to your app's dashboard: https://dashboard.heroku.com/apps/YOUR_APP_NAME
2. Click on the **Resources** tab
3. In the "Add-ons" search box, type **Heroku Scheduler**
4. Click on "Heroku Scheduler" and click "Submit Order Form" (it's free)

### Via Heroku CLI:
```bash
heroku addons:create scheduler:standard -a YOUR_APP_NAME
```

## Step 2: Set Environment Variables

You need to set two environment variables in your Heroku app:

### Via Heroku Dashboard:
1. Go to your app's **Settings** tab
2. Click **Reveal Config Vars**
3. Add these variables:

| Key | Value |
|-----|-------|
| `CRON_SECRET_TOKEN` | Generate a secure token (see below) |
| `APP_URL` | Your app's URL (e.g., `https://your-app-name.herokuapp.com`) |

### Via Heroku CLI:
```bash
# Generate a secure token
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Set the environment variables (replace with your values)
heroku config:set CRON_SECRET_TOKEN="your-generated-token-here" -a YOUR_APP_NAME
heroku config:set APP_URL="https://your-app-name.herokuapp.com" -a YOUR_APP_NAME
```

## Step 3: Add requests to requirements.txt

Make sure `requests` is in your `requirements.txt` file:

```bash
# Check if it's already there
grep requests requirements.txt

# If not, add it
echo "requests" >> requirements.txt
```

Then commit and push:
```bash
git add requirements.txt
git commit -m "Add requests dependency for scheduler"
git push heroku main
```

## Step 4: Configure the Scheduler Job

### Via Heroku Dashboard:
1. Go to your app's **Resources** tab
2. Click on **Heroku Scheduler** (in the Add-ons section)
3. Click **Create job**
4. Configure the job:
   - **Schedule**: Select the time you want summaries sent (e.g., "8:00 PM UTC")
   - **Frequency**: Daily
   - **Run Command**: `python send_daily_summaries.py`
5. Click **Save**

### Via Heroku CLI:
```bash
# Open the scheduler dashboard
heroku addons:open scheduler -a YOUR_APP_NAME
```
Then follow the dashboard instructions above.

## Step 5: Test the Setup

### Test Immediately (Don't wait for scheduled time):

#### Via Heroku Dashboard:
1. Go to Heroku Scheduler (Resources → Heroku Scheduler)
2. Find your job
3. Click the **⋮** (three dots) menu
4. Click **Run now**

#### Via Heroku CLI:
```bash
# Run the script manually to test
heroku run python send_daily_summaries.py -a YOUR_APP_NAME
```

### Check the Logs:
```bash
heroku logs --tail -a YOUR_APP_NAME
```

Look for output like:
```
Sending daily meal plan summaries...
✓ Success! Processed 2 households
  ✓ Household 1: success
  ✓ Household 2: success
```

## Step 6: Verify Email Delivery

1. Add a test meal to your meal plan
2. Wait for the scheduled job to run (or run it manually)
3. Check your email for the daily summary

## Troubleshooting

### Job Not Running
- Check the scheduler logs in the Heroku Scheduler dashboard
- Verify the job is enabled (not paused)
- Check your app logs: `heroku logs --tail -a YOUR_APP_NAME`

### "CRON_SECRET_TOKEN not set" Error
- Verify the config var is set: `heroku config -a YOUR_APP_NAME`
- Make sure there are no typos in the variable name

### "Connection Error" or Timeout
- Verify `APP_URL` is correct and includes `https://`
- Check if your app is sleeping (free dynos sleep after 30 min of inactivity)
- Consider upgrading to a paid dyno if using free tier

### No Emails Sent
- Verify email configuration:
  ```bash
  heroku config:get MAIL_USERNAME -a YOUR_APP_NAME
  heroku config:get MAIL_PASSWORD -a YOUR_APP_NAME
  heroku config:get MAIL_DEFAULT_SENDER -a YOUR_APP_NAME
  ```
- Check if there are actually changes to report (add a test meal first)
- Check app logs for email errors

### "401 Unauthorized" Error
- The `CRON_SECRET_TOKEN` in your config vars doesn't match
- Regenerate the token and update both the config var and test it

## Recommended Schedule

**Best time to send**: Evening (7-8 PM in your users' timezone)

For example, if your users are in EST (UTC-5):
- Set scheduler to **1:00 AM UTC** (8:00 PM EST)
- Or **2:00 AM UTC** (9:00 PM EST)

**Note**: Heroku Scheduler runs in UTC timezone, so convert your desired local time to UTC.

## Monitoring

### View Scheduler History:
1. Go to Heroku Scheduler dashboard
2. Click on your job
3. View the "Recent runs" section

### Set Up Alerts (Optional):
Consider using Heroku's logging add-ons or external monitoring:
- **Papertrail** - Log management
- **Sentry** - Error tracking
- **New Relic** - Performance monitoring

## Cost

- **Heroku Scheduler**: Free
- **Dyno usage**: Scheduler jobs use dyno hours
  - Free tier: 550 dyno hours/month (plenty for daily jobs)
  - Paid tier: Unlimited

## Alternative: Direct Cron Approach

If you prefer not to use Heroku Scheduler, you can use an external cron service:

### Using cron-job.org (Free):
1. Sign up at https://cron-job.org
2. Create a new cron job:
   - **URL**: `https://your-app-name.herokuapp.com/meal-plan/send-daily-summaries`
   - **Schedule**: Daily at your preferred time
   - **HTTP Method**: POST
   - **Headers**: Add `X-Cron-Token: your-token-here`

### Using EasyCron (Free tier available):
1. Sign up at https://www.easycron.com
2. Create a cron job with similar settings as above

## Next Steps

After setup is complete:
1. Monitor the first few runs to ensure everything works
2. Check with household members that they're receiving emails
3. Adjust the schedule time if needed based on user feedback

## Questions?

Check the main documentation: `MEAL_PLAN_NOTIFICATIONS_README.md`

