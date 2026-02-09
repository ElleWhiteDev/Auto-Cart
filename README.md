# Auto-Cart 🛒

> **A modern, full-stack grocery list management application with AI-powered recipe parsing and Kroger API integration**

[![Live Demo](https://img.shields.io/badge/demo-live-success)](http://www.ellewhite.dev)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-2.3+-green.svg)](https://flask.palletsprojects.com/)
[![PostgreSQL](https://img.shields.io/badge/postgresql-latest-blue.svg)](https://www.postgresql.org/)

## 🌐 Live Site

**[www.ellewhite.dev](http://www.ellewhite.dev)**

## 📋 Overview

Auto-Cart is a sophisticated web application that streamlines meal planning and grocery shopping. Built with modern software engineering principles, it features AI-powered recipe extraction, intelligent ingredient consolidation, multi-household support, and seamless Kroger API integration for one-click cart population.

### Key Highlights for Employers

- **Clean Architecture**: Service layer pattern with clear separation of concerns
- **Modern Python**: Type hints, comprehensive error handling, and professional logging
- **RESTful API Design**: Standardized JSON responses with proper HTTP status codes
- **Database Design**: Well-normalized PostgreSQL schema with proper relationships and constraints
- **Security**: Bcrypt password hashing, OAuth 2.0 integration, CSRF protection
- **Scalability**: Multi-household support with role-based access control
- **AI Integration**: OpenAI API for intelligent recipe parsing and ingredient standardization
- **Production Ready**: Deployed on Heroku with environment-based configuration

## ✨ Features

### Core Functionality
- 🔐 **Secure Authentication**: User registration, login, and profile management with bcrypt encryption
- 📖 **Recipe Management**: Store, organize, and share recipes within households
- 🛒 **Smart Grocery Lists**: AI-powered ingredient consolidation (e.g., "1 cup milk" + "2 cups milk" = "3 cups milk")
- 🏪 **Kroger Integration**: One-click export to Kroger shopping cart via OAuth 2.0
- 📅 **Meal Planning**: Weekly meal planner with cook assignments and notifications
- 👥 **Multi-Household Support**: Manage multiple households (family, roommates, vacation homes)
- 🤖 **AI Recipe Extraction**: Automatically parse recipes from any URL using OpenAI
- 📧 **Email Integration**: Grocery list delivery and daily meal plan summaries
- 🗣️ **Alexa Integration**: Voice-controlled grocery list management

### Technical Features
- **Responsive Design**: Mobile-first CSS with custom design system
- **Real-time Updates**: AJAX-powered interactions without page reloads
- **Shopping Mode**: Live collaborative shopping with item checking
- **Role-Based Access**: Household owners and members with different permissions
- **Audit Trail**: Track who created/modified recipes and lists

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
├── services/              # Service layer (NEW)
│   ├── recipe_service.py
│   ├── grocery_list_service.py
│   ├── meal_plan_service.py
│   └── api_response.py
├── static/
│   ├── js/
│   │   └── main.js        # Organized frontend JavaScript
│   └── stylesheets/
│       ├── design-system.css
│       └── style.css
├── templates/             # Jinja2 HTML templates
└── requirements.txt       # Python dependencies
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
- Recipes and grocery lists are scoped to households
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
4. **Build Grocery List**: Select recipes to automatically generate a consolidated shopping list
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

```bash
# Run tests (when implemented)
pytest

# Check code style
flake8 .

# Type checking
mypy .
```

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

- [ ] Unit and integration test suite
- [ ] Recipe sharing between households
- [ ] Nutrition information integration
- [ ] Recipe ratings and reviews
- [ ] Barcode scanning for pantry management
- [ ] Recipe recommendations based on available ingredients
- [ ] Export to other grocery store APIs
- [ ] Mobile native apps (iOS/Android)

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
