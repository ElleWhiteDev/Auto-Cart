# Security Policy

## Supported Versions

Currently supported versions of Auto-Cart:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Security Features

Auto-Cart implements multiple layers of security to protect user data and prevent common vulnerabilities.

### Authentication & Authorization

- **Password Hashing**: All passwords are hashed using bcrypt with salt
- **Session Management**: Secure session cookies with configurable expiration
- **Persistent Login**: Optional "remember me" functionality with secure tokens
- **Password Reset**: Time-limited reset tokens (1 hour expiration)
- **Role-Based Access Control**: Household owners and members with different permissions

### Data Protection

- **SQL Injection Prevention**: SQLAlchemy ORM with parameterized queries
- **XSS Protection**: Jinja2 automatic HTML escaping
- **CSRF Protection**: Flask-WTF CSRF tokens on all forms
- **Input Validation**: Server-side validation on all user inputs
- **Email Enumeration Prevention**: Generic messages for password reset

### API Security

- **OAuth 2.0**: Secure third-party authentication with Kroger API
- **Token Management**: Secure storage and refresh of OAuth tokens
- **API Key Protection**: Environment variables for sensitive credentials
- **HTTPS**: Production deployment uses HTTPS (Heroku)

### Database Security

- **Connection Pooling**: SQLAlchemy connection pooling
- **Prepared Statements**: Parameterized queries prevent SQL injection
- **Data Scoping**: All data scoped to households for multi-tenancy
- **Cascade Deletes**: Proper cleanup of related data

### Application Security

- **Environment Variables**: Sensitive data in .env files (not committed)
- **Secret Key**: Cryptographically secure secret key for sessions
- **Error Handling**: Generic error messages to prevent information leakage
- **Logging**: Security events logged for audit trail
- **Admin Access**: Separate admin authentication and authorization

## Known Limitations

The following security enhancements are planned for future releases:

- **Rate Limiting**: Not currently implemented (planned)
- **Two-Factor Authentication**: Not currently implemented (planned)
- **AJAX CSRF**: Some AJAX endpoints lack CSRF protection (planned)
- **Content Security Policy**: Not currently implemented (planned)
- **Security Headers**: Additional security headers needed (planned)

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report security vulnerabilities by emailing:

**ellewhitedev@gmail.com**

Include the following information:

- Type of vulnerability
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the vulnerability

### What to Expect

- **Acknowledgment**: You will receive an acknowledgment within 48 hours
- **Updates**: You will receive updates on the progress every 5-7 days
- **Disclosure**: We aim to fix critical vulnerabilities within 90 days
- **Credit**: You will be credited for the discovery (unless you prefer to remain anonymous)

## Security Best Practices for Deployment

### Environment Variables

Never commit the following to version control:

- `SECRET_KEY` - Generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- `OPENAI_API_KEY` - Your OpenAI API key
- `CLIENT_ID` / `CLIENT_SECRET` - Kroger API credentials
- `MAIL_PASSWORD` - Email account password
- Database connection strings

### Production Configuration

- Use PostgreSQL (not SQLite) in production
- Enable HTTPS (automatic on Heroku)
- Set strong `SECRET_KEY` (32+ characters)
- Use environment-specific configuration
- Enable logging and monitoring
- Regular database backups
- Keep dependencies updated

### User Data Protection

- Never log passwords or tokens
- Sanitize user input before display
- Validate all file uploads (if implemented)
- Implement proper access controls
- Regular security audits

## Security Checklist for Contributors

Before submitting a pull request:

- [ ] No hardcoded secrets or API keys
- [ ] User input is validated and sanitized
- [ ] SQL queries use parameterized statements
- [ ] Authentication required for protected routes
- [ ] Authorization checks for user-owned resources
- [ ] Error messages don't leak sensitive information
- [ ] New dependencies are from trusted sources
- [ ] Tests include security scenarios

## Compliance

Auto-Cart is designed with the following security standards in mind:

- **OWASP Top 10**: Protection against common web vulnerabilities
- **GDPR Considerations**: User data can be deleted on request
- **Password Security**: NIST password guidelines (bcrypt, no complexity requirements)

## Security Updates

Security updates will be documented in [CHANGELOG.md](CHANGELOG.md) and released as patch versions.

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Flask Security Best Practices](https://flask.palletsprojects.com/en/2.3.x/security/)
- [SQLAlchemy Security](https://docs.sqlalchemy.org/en/20/faq/security.html)

---

**Last Updated**: 2024-01-15

