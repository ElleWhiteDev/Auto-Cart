# Changelog

All notable changes to Auto-Cart will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive test suite with pytest
  - Unit tests for database models
  - Integration tests for HTTP routes
  - Service layer tests
  - Test fixtures and configuration
- Professional project documentation
  - LICENSE (MIT)
  - CONTRIBUTING.md with development guidelines
  - CODE_OF_CONDUCT.md
  - API_DOCUMENTATION.md with endpoint specifications
  - scripts/README.md for migration scripts
- Testing dependencies (pytest, pytest-cov, pytest-flask, pytest-mock)
- Code quality tools (black, flake8, mypy)
- .env.example template for environment configuration

### Changed
- Organized project structure
  - Moved migration scripts to `/scripts` directory
  - Created `/tests` directory for test suite
- Updated README.md with testing instructions and coverage information
- Enhanced requirements.txt with testing and code quality dependencies

### Fixed
- Mobile grocery list editing UI
  - Compact input fields for mobile screens
  - Enter key saves immediately from any field
  - Auto-save on blur (keyboard close)
  - Hidden save/cancel buttons on mobile for more space

## [1.0.0] - 2024-01-15

### Added
- Similar Recipes feature
  - AI-powered recipe matching based on grocery list ingredients
  - Modal UI with expandable recipe cards
  - Automatic meal plan integration
- Feature announcement email system
  - HTML email templates
  - Admin dashboard integration
- Multi-household support
  - Users can belong to multiple households
  - Household-scoped recipes and grocery lists
  - Role-based access (owners and members)
- Kroger API integration
  - OAuth 2.0 authentication
  - One-click cart population
  - Product search and location services
- AI-powered recipe extraction
  - OpenAI GPT integration
  - Automatic ingredient parsing
  - Smart quantity consolidation
- Meal planning system
  - Weekly calendar view
  - Multiple cook assignments per meal
  - Custom meals without recipes
  - Daily email summaries
- Grocery list management
  - Intelligent ingredient consolidation
  - Shopping mode with real-time updates
  - Email delivery
  - Editable quantities and names
- User authentication
  - Secure password hashing with bcrypt
  - Password reset functionality
  - Persistent login sessions
- Alexa integration
  - Voice-controlled grocery list management

### Security
- Bcrypt password hashing
- OAuth 2.0 for third-party authentication
- CSRF protection on forms
- SQL injection prevention via SQLAlchemy ORM
- XSS protection via Jinja2 auto-escaping

## [0.1.0] - Initial Development

### Added
- Basic Flask application structure
- SQLAlchemy database models
- User registration and login
- Recipe management
- Basic grocery list functionality

---

## Version History

- **1.0.0** - Production release with full feature set
- **0.1.0** - Initial development version

## Upgrade Notes

### Upgrading to 1.0.0
- Run database migrations in `/scripts` directory
- Update environment variables (see `.env.example`)
- Install new dependencies: `pip install -r requirements.txt`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on contributing to this project.

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

