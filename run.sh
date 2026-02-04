#!/bin/bash

# Auto-Cart Quick Start Script
# This script helps you get the app running quickly

echo "🛒 Auto-Cart Quick Start"
echo "========================"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found!"
    echo "📝 Creating .env from .env.example..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit the .env file with your actual API keys and credentials!"
    echo "   Required:"
    echo "   - DATABASE_URL (or use SQLite default)"
    echo "   - OPENAI_API_KEY"
    echo "   - CLIENT_ID and CLIENT_SECRET (Kroger API)"
    echo "   - MAIL_USERNAME and MAIL_PASSWORD (Gmail)"
    echo ""
    read -p "Press Enter after you've updated the .env file..."
fi

# Install dependencies
echo "📚 Installing dependencies..."
pip install -q -r requirements.txt
echo "✅ Dependencies installed"

# Check if database needs initialization
echo "🗄️  Checking database..."
if [ ! -f "autocart.db" ] && [[ $DATABASE_URL == *"sqlite"* ]]; then
    echo "📊 Initializing database..."
    python -c "from app import app, db; app.app_context().push(); db.create_all(); print('✅ Database initialized')"
fi

echo ""
echo "🚀 Starting Auto-Cart..."
echo "📱 Access the app at: http://localhost:5000"
echo "📱 For mobile testing, use: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Run the app
python app.py

