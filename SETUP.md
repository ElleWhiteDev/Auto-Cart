# Auto-Cart Setup Guide 🚀

This guide will help you get Auto-Cart running locally on your machine.

## Prerequisites

- Python 3.8 or higher
- PostgreSQL database
- Kroger Developer Account (for API access)
- OpenAI API Key
- Gmail account (for email functionality)

## Step 1: Clone and Navigate to Project

```bash
cd /home/ewhite/Auto-Cart
```

## Step 2: Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate
```

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 4: Set Up Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit the `.env` file and add your API keys:

```env
# Flask Configuration
SECRET_KEY=your-secret-key-here
FLASK_ENV=development

# Database Configuration
# App automatically detects environment using DYNO env var (set by Heroku)
# For local development (used when DYNO is not set)
LOCAL_DATABASE_CONN=sqlite:///autocart.db
# For Heroku (used when DYNO is set)
HEROKU_DATABASE_CONN=postgres://your-heroku-db-url

# Kroger API Configuration
CLIENT_ID=your-kroger-client-id
CLIENT_SECRET=your-kroger-client-secret
OAUTH2_BASE_URL=https://api.kroger.com/v1
REDIRECT_URL=http://localhost:5000/kroger/callback

# OpenAI API Configuration
OPENAI_API_KEY=your-openai-api-key

# Email Configuration (Gmail)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-specific-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
```

**Important:** The app **automatically detects** the environment:
- **Local Development**: Checks for `DYNO` environment variable (not set locally)
  - Uses `LOCAL_DATABASE_CONN` (defaults to SQLite)
- **Heroku Production**: Heroku automatically sets `DYNO` environment variable
  - Uses `HEROKU_DATABASE_CONN` (PostgreSQL)

**No need to comment/uncomment anything!** The app automatically uses the right database based on where it's running.

## Step 5: Database Setup (Automatic!)

No manual database setup needed! The app will:
- **Locally**: Create a SQLite database (`autocart.db`) automatically on first run
- **On Heroku**: Use PostgreSQL from `HEROKU_DATABASE_CONN`

The environment is detected automatically using the `DYNO` environment variable that Heroku sets.

## Step 7: Run the Application

```bash
# Development mode
python app.py

# Or using Flask CLI
flask run
```

The app should now be running at: **http://localhost:5000**

## Step 8: Access the Application

1. Open your browser and go to `http://localhost:5000`
2. Register a new account
3. Start adding recipes!

## API Setup Instructions

### Kroger API Setup

1. Go to [Kroger Developer Portal](https://developer.kroger.com/)
2. Create an account and register a new application
3. Copy your `CLIENT_ID` and `CLIENT_SECRET`
4. Set redirect URL to `http://localhost:5000/kroger/callback`
5. Add these to your `.env` file

### OpenAI API Setup

1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Create an account and generate an API key
3. Add the key to your `.env` file as `OPENAI_API_KEY`

### Gmail App Password Setup

1. Enable 2-Factor Authentication on your Gmail account
2. Go to Google Account Settings → Security → App Passwords
3. Generate a new app password for "Mail"
4. Use this password in your `.env` file (not your regular Gmail password)

## Troubleshooting

### Database Connection Issues

If you get database connection errors:
```bash
# Check PostgreSQL is running
sudo service postgresql status

# Start PostgreSQL if needed
sudo service postgresql start
```

### Port Already in Use

If port 5000 is already in use:
```bash
# Run on a different port
flask run --port 5001
```

### Missing Environment Variables

If you get errors about missing environment variables, make sure:
- Your `.env` file is in the project root
- All required variables are set
- You've activated your virtual environment

## Mobile Testing

To test on your phone while running locally:

1. Find your computer's local IP address:
   ```bash
   # Linux/Mac
   ifconfig | grep "inet "
   # Or
   hostname -I
   ```

2. Run Flask with host binding:
   ```bash
   flask run --host=0.0.0.0
   ```

3. Access from your phone using:
   ```
   http://YOUR_IP_ADDRESS:5000
   ```

## Next Steps

- Add your first recipe by URL
- Test the Kroger integration
- Try the email export feature
- Explore the mobile-friendly interface!

## Need Help?

Check the logs in the console for detailed error messages. The app uses comprehensive logging to help debug issues.
