# Auto-Cart 🛒

> **A modern, full-stack pantry list management application with AI-powered recipe parsing and Kroger API integration**

[![Live Demo](https://img.shields.io/badge/demo-live-success)](http://www.ellewhite.dev)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-2.3+-green.svg)](https://flask.palletsprojects.com/)
[![PostgreSQL](https://img.shields.io/badge/postgresql-latest-blue.svg)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](https://docs.pytest.org/)

## 🌐 Live Site

**[www.ellewhite.dev](http://www.ellewhite.dev)**

## 📋 Overview

Auto-Cart is a sophisticated web application that streamlines meal planning and pantry planning. Built with modern software engineering principles, it features AI-powered recipe extraction, intelligent ingredient consolidation, multi-household support, and seamless Kroger API integration for one-click cart population.

## 📚 Documentation

- **[Setup Guide](SETUP.md)** - Detailed installation and configuration instructions
- **[Architecture](ARCHITECTURE.md)** - System design and architectural patterns
- **[API Documentation](API_DOCUMENTATION.md)** - HTTP endpoints and request/response formats
- **[Security Policy](SECURITY.md)** - Security features and vulnerability reporting
- **[Changelog](CHANGELOG.md)** - Version history and release notes
- **[Multi-Household Guide](MULTI_HOUSEHOLD_GUIDE.md)** - Guide to multi-household features

### Key Highlights

- **Clean Architecture**: Service layer pattern with clear separation of concerns
- **Modern Python**: Type hints, comprehensive error handling, and professional logging
- **RESTful API Design**: Standardized JSON responses with proper HTTP status codes
- **Database Design**: Well-normalized PostgreSQL schema with proper relationships and constraints
- **Security**: Bcrypt password hashing, OAuth 2.0 integration, CSRF protection
- **Scalability**: Multi-household support with role-based access control
- **AI Integration**: OpenAI API for intelligent recipe parsing and ingredient standardization
- **Production Ready**: Deployed on Heroku with environment-based configuration
- **Comprehensive Testing**: pytest suite with unit, integration, and service layer tests

## ✨ Features

### Core Functionality
- 🔐 **Secure Authentication**: User registration, login, and profile management with bcrypt encryption
  - Password reset via email with secure tokens
  - Persistent login sessions
  - Profile customization (username, email, password)
- 📖 **Recipe Management**: Store, organize, and share recipes within households
  - AI-powered recipe extraction from any URL
  - Manual recipe entry with ingredient parsing
  - Recipe editing and deletion (household owners)
  - Recipe notes and source URL tracking
- 🛒 **Smart Pantry Lists**: AI-powered ingredient consolidation
  - Automatic quantity consolidation (e.g., "1 cup milk" + "2 cups milk" = "3 cups milk")
  - **Editable grocery items** - Edit quantity, measurement, and ingredient name inline
  - Mobile-optimized editing with Enter key to save
  - Real-time item checking/unchecking
  - Email pantry lists to anyone
- 🏪 **Kroger Integration**: One-click export to Kroger shopping cart via OAuth 2.0
  - Product search and matching
  - Store location services
  - Direct cart population
  - Per-household Kroger account linking
- 📅 **Meal Planning**: Weekly meal planner with advanced features
  - **Multiple cook assignments** per meal
  - **Custom meals** without recipes
  - Daily email summaries with meal details
  - Chef assignment notifications
  - Meal plan change tracking
  - Export meal plan to pantry list
- 🧾 **Manual Ingredients**: Paste or type a single ingredient line, have Auto-Cart parse and consolidate it via AI, and add it without leaving the page.
- 🧠 **Recipe Editing Flow**: The recipe editor now shows instant loading feedback and redirects back to your profile when saved.
- ⚡ **Real-Time Collaboration**: Household members now stay in sync as edits flow through instantly, especially in recipes and pantry lists.
- 🤖 **Similar Recipes**: AI-powered recipe recommendations
  - Analyzes current meal plan ingredients
  - Suggests recipes with 25%+ ingredient overlap
  - One-click add to meal plan
  - Helps reduce pantry list size
- 👥 **Multi-Household Support**: Manage multiple households
  - Create unlimited households (family, roommates, vacation homes)
  - Role-based access (owners and members)
  - Switch between households seamlessly
  - Household-scoped recipes and pantry lists
  - Invite members via email
- 📧 **Email Integration**: Comprehensive email features
  - Pantry list delivery
  - Daily meal plan summaries
  - Chef assignment notifications
  - Password reset emails
  - Feature announcements (admin)
  - Customizable email preferences
- 🗣️ **Alexa Integration**: Voice-controlled pantry list management
  - Add items via voice
  - Check items off list
  - Hear pantry list read aloud

### Technical Features
- **Responsive Design**: Mobile-first CSS with custom design system
  - Touch-friendly UI optimized for phones and tablets
  - Compact mobile layouts for grocery editing
  - Progressive Web App capabilities
- **Real-time Updates**: AJAX-powered interactions without page reloads
  - Instant item checking/unchecking
  - Live pantry list updates
  - Seamless recipe additions
- **Shopping Mode**: Dedicated shopping interface
  - Large, touch-friendly checkboxes
  - Progress tracking
  - Auto-remove checked items on completion
  - Distraction-free shopping experience
- **Admin Dashboard**: Comprehensive admin tools
  - User management and statistics
  - Household overview and analytics
  - Feature announcement system
  - Database migration tools
  - User activity tracking
- **Role-Based Access**: Household owners and members with different permissions
  - Owners can delete recipes and manage household
  - Members can add recipes and use features
  - Secure permission checks on all operations
- **Audit Trail**: Track who created/modified recipes and lists
  - Created by user tracking
  - Last modified timestamps
  - Activity logging

## 🏗️ Architecture

### Technology Stack

**Backend**
- **Framework**: Flask 2.3+ (Python)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: Flask-Bcrypt, OAuth 2.0
- **Email**: Flask-Mail with SMTP
- **AI**: OpenAI GPT for recipe parsing
- **Deployment**: Gunicorn on Heroku

**Frontend**
- **HTML5** with Jinja2 templating
- **CSS3** with custom design system (CSS variables, mobile-first)
- **JavaScript** (ES6+) with modular architecture
- **Icons**: Font Awesome 6

**External APIs**
- Kroger API (Auth, Product Search, Cart, Location, Store)
- OpenAI API (GPT-4 for recipe intelligence)
- Amazon Alexa Skills Kit

### Project Structure

```
Auto-Cart/
├── app.py                 # Main application and routes
├── models.py              # Database models and business logic
├── forms.py               # WTForms form definitions
├── utils.py               # Utility functions and decorators
├── kroger.py              # Kroger API service layer
├── recipe_scraper.py      # Web scraping for recipes
├── alexa_api.py           # Alexa Skills Kit integration
├── services/              # Service layer
│   ├── recipe_service.py
│   ├── grocery_list_service.py
│   ├── meal_plan_service.py
│   └── api_response.py
├── tests/                 # Test suite
│   ├── conftest.py        # Test fixtures and configuration
│   ├── test_models.py     # Unit tests for models
│   ├── test_services.py   # Service layer tests
│   └── test_routes.py     # Integration tests for routes
├── scripts/               # Database migrations and utilities
│   ├── README.md          # Migration documentation
│   ├── migrate_*.py       # Database migration scripts
│   └── send_daily_summaries.py  # Scheduled email task
├── static/
│   ├── js/                # Frontend JavaScript
│   └── stylesheets/
│       ├── design-system.css  # Design system and components
│       └── style.css          # Application styles
├── templates/             # Jinja2 HTML templates
│   ├── base.html          # Base template
│   ├── index.html         # Homepage with recipe box
│   ├── meal_plan.html     # Meal planning interface
│   ├── shopping_mode.html # Shopping mode UI
│   └── admin_dashboard.html  # Admin interface
├── pytest.ini             # Pytest configuration
├── requirements.txt       # Python dependencies
├── .env.example           # Environment variable template
├── LICENSE                # MIT License
├── CONTRIBUTING.md        # Contribution guidelines
├── CODE_OF_CONDUCT.md     # Code of conduct
├── CHANGELOG.md           # Version history
└── API_DOCUMENTATION.md   # API endpoint reference
```

### Database Schema

**Core Models**
- `User`: Authentication and profile data
- `Household`: Multi-household support with shared resources
- `HouseholdMember`: Association table with roles (owner/member)
- `Recipe`: Recipe storage with metadata
- `RecipeIngredient`: Parsed ingredients with quantity/measurement
- `GroceryList`: Shopping lists scoped to households
- `GroceryListItem`: Individual items with checked status
- `MealPlanEntry`: Weekly meal planning with cook assignments

**Key Relationships**
- Users can belong to multiple households
- Households can have multiple owners and members
- Recipes and pantry lists are scoped to households
- Meal plans support cook assignments and custom meals

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- PostgreSQL (or SQLite for development)
- Kroger Developer Account (for API keys)
- OpenAI API Key (for AI features)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/ElleWhiteDev/Auto-Cart.git
   cd Auto-Cart
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**

   Create a `.env` file in the root directory:
   ```env
   # Flask Configuration
   SECRET_KEY=your-secret-key-here
   FLASK_ENV=development

   # Database
   LOCAL_DATABASE_CONN=postgresql://user:password@localhost/autocart
   # Or use SQLite for development:
   # LOCAL_DATABASE_CONN=sqlite:///autocart.db

   # Kroger API
   CLIENT_ID=your-kroger-client-id
   CLIENT_SECRET=your-kroger-client-secret
   OAUTH2_BASE_URL=https://api.kroger.com/v1/connect/oauth2
   LOCAL_REDIRECT_URL=http://localhost:5000/callback

   # OpenAI API
   OPENAI_API_KEY=your-openai-api-key

   # Email Configuration (optional)
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=true
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=your-app-password
   MAIL_DEFAULT_SENDER=your-email@gmail.com
   ```

5. **Initialize the database**
   ```bash
   python
   >>> from app import app, db
   >>> with app.app_context():
   ...     db.create_all()
   >>> exit()
   ```

6. **Run the application**
   ```bash
   flask run
   # Or use the provided script:
   ./run.sh
   ```

7. **Access the application**

   Open your browser to `http://localhost:5000`

## 💡 Usage

### Basic Workflow

1. **Register/Login**: Create an account or sign in
2. **Create Household**: Set up your household (family, roommates, etc.)
3. **Add Recipes**:
   - Paste a recipe URL and let AI extract the data
   - Or manually enter recipe details
   - Use AI to standardize ingredient formatting
4. **Build Pantry List**: Select recipes to automatically generate a consolidated shopping list
5. **Shop**:
   - Export to Kroger cart with one click
   - Or email the list to yourself
   - Use shopping mode for real-time item checking

### Advanced Features

**Multi-Household Management**
- Create separate households for different contexts (home, vacation, parents)
- Share recipes and lists with household members
- Assign different Kroger accounts per household

**Meal Planning**
- Plan meals for the week
- Assign cooks to specific meals
- Add custom meals without recipes
- Receive daily email summaries

**AI-Powered Features**
- Automatic recipe extraction from any URL
- Intelligent ingredient parsing and standardization
- Smart quantity consolidation

## 🔧 Development

### Code Quality

- **Type Hints**: Comprehensive type annotations for better IDE support
- **Error Handling**: Consistent error handling with proper logging
- **DRY Principles**: Service layer to eliminate code duplication
- **Documentation**: Docstrings following Google style guide
- **Security**: Input validation, CSRF protection, secure password storage

### Testing

The project includes a comprehensive test suite with unit tests, integration tests, and service layer tests.

```bash
# Install testing dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run tests with coverage report
pytest --cov=. --cov-report=html --cov-report=term-missing

# Run specific test categories
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m service       # Service layer tests only

# Run tests in verbose mode
pytest -v

# Check code style
flake8 .

# Format code
black .

# Type checking
mypy .
```

**Test Structure:**
- `tests/test_models.py` - Unit tests for database models
- `tests/test_services.py` - Tests for service layer business logic
- `tests/test_routes.py` - Integration tests for HTTP endpoints
- `tests/conftest.py` - Shared fixtures and test configuration

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📊 Performance & Scalability

- **Database Optimization**: Proper indexing and eager loading to prevent N+1 queries
- **Caching**: Session-based caching for API responses
- **Async Operations**: Background tasks for email sending
- **Connection Pooling**: SQLAlchemy connection pooling for database efficiency

## 🔐 Security Features

- **Password Security**: Bcrypt hashing with salt
- **OAuth 2.0**: Secure third-party authentication with Kroger
- **CSRF Protection**: Flask-WTF CSRF tokens on all forms
- **Input Validation**: Server-side validation on all user inputs
- **SQL Injection Prevention**: SQLAlchemy ORM with parameterized queries
- **XSS Protection**: Jinja2 auto-escaping

## 📱 Mobile Support

- **Progressive Web App**: Add to home screen for app-like experience
- **Responsive Design**: Mobile-first CSS with touch-friendly UI
- **Offline Capability**: Service workers for offline recipe viewing (planned)

## 🎯 Future Enhancements

- [x] ~~Unit and integration test suite~~ ✅ **COMPLETED**
- [x] ~~Similar recipe recommendations~~ ✅ **COMPLETED**
- [x] ~~Editable pantry list items~~ ✅ **COMPLETED**
- [x] ~~Password reset functionality~~ ✅ **COMPLETED**
- [x] ~~Admin dashboard~~ ✅ **COMPLETED**
- [ ] Recipe sharing between households
- [ ] Nutrition information integration
- [ ] Recipe ratings and reviews
- [ ] Barcode scanning for pantry management
- [ ] Export to other grocery store APIs (Walmart, Target, etc.)
- [ ] Mobile native apps (iOS/Android)
- [ ] Recipe import from popular sites (AllRecipes, Food Network, etc.)
- [ ] Meal plan templates (Keto, Vegan, etc.)
- [ ] Grocery budget tracking
- [ ] Recipe scaling (2x, 3x servings)
- [ ] Print-friendly recipe cards

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👤 Author

**Elle White**
- Portfolio: [www.ellewhite.dev](http://www.ellewhite.dev)
- GitHub: [@ElleWhiteDev](https://github.com/ElleWhiteDev)
- LinkedIn: [Elle White](https://www.linkedin.com/in/ellewhitedev)

## 🙏 Acknowledgments

- Kroger Developer Program for API access
- OpenAI for GPT API
- Flask and SQLAlchemy communities
- All open-source contributors

---

**Built with ❤️ by Elle White | Showcasing modern full-stack development practices**
