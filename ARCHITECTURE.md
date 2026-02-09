# Auto-Cart Architecture Documentation

## System Overview

Auto-Cart is a full-stack web application built with Flask (Python) that demonstrates modern software engineering practices including service-oriented architecture, RESTful API design, and clean code principles.

## Architecture Patterns

### 1. Service Layer Pattern

The application implements a service layer to separate business logic from route handlers:

```
Routes (app.py) → Services → Models → Database
                     ↓
                 Utilities
```

**Benefits:**
- **Separation of Concerns**: Business logic is isolated from HTTP handling
- **Reusability**: Services can be called from multiple routes or background tasks
- **Testability**: Services can be unit tested independently
- **Maintainability**: Changes to business logic don't affect route structure

**Service Classes:**
- `RecipeService`: Recipe CRUD operations and ingredient parsing
- `GroceryListService`: List management and ingredient consolidation
- `MealPlanService`: Meal planning and weekly view generation
- `APIResponse`: Standardized JSON response formatting

### 2. Repository Pattern (via SQLAlchemy ORM)

Database access is abstracted through SQLAlchemy models, providing:
- Type-safe database queries
- Automatic SQL generation
- Connection pooling
- Transaction management

### 3. Decorator Pattern

Custom decorators for cross-cutting concerns:
- `@require_login`: Authentication enforcement
- `@require_admin`: Authorization checks
- `@app.before_request`: Global request preprocessing

## Data Flow

### Recipe Creation Flow

```
User Input → Form Validation → RecipeService.create_recipe()
                                        ↓
                                Parse Ingredients (OpenAI)
                                        ↓
                                Create Recipe Model
                                        ↓
                                Create RecipeIngredient Models
                                        ↓
                                Database Commit
                                        ↓
                                Return Success/Error
```

### Kroger Integration Flow

```
User Selects Recipes → Build Grocery List → Consolidate Ingredients
                                                    ↓
                                            OAuth Authentication
                                                    ↓
                                            Search Products (Kroger API)
                                                    ↓
                                            User Selects Products
                                                    ↓
                                            Add to Cart (Kroger API)
                                                    ↓
                                            Redirect to Kroger Checkout
```

## Database Design

### Entity Relationship Diagram

```
User ←→ HouseholdMember ←→ Household
                              ↓
                    ┌─────────┼─────────┐
                    ↓         ↓         ↓
                 Recipe  GroceryList  MealPlanEntry
                    ↓         ↓
            RecipeIngredient  GroceryListItem
```

### Key Design Decisions

1. **Multi-Household Support**: Users can belong to multiple households via `HouseholdMember` association table
2. **Household Scoping**: Recipes, lists, and meal plans are scoped to households for data isolation
3. **Soft Ownership**: Households can have multiple owners for flexibility
4. **Audit Trail**: `created_by_user_id` and `last_modified_by_user_id` on key tables

### Normalization

- **3NF Compliance**: All tables are in third normal form
- **No Redundancy**: Ingredient data is normalized across recipes
- **Referential Integrity**: Foreign key constraints ensure data consistency

## API Integration

### Kroger API

**Authentication Flow:**
1. OAuth 2.0 Authorization Code Grant
2. Token storage in user model
3. Automatic token refresh (planned)

**API Endpoints Used:**
- `/connect/oauth2/authorize` - User authorization
- `/connect/oauth2/token` - Token exchange
- `/products` - Product search
- `/cart/add` - Add items to cart
- `/locations` - Store locator

**Error Handling:**
- Graceful degradation when API is unavailable
- User-friendly error messages
- Logging for debugging

### OpenAI API

**Use Cases:**
1. Recipe extraction from URLs
2. Ingredient standardization
3. Quantity parsing and normalization

**Implementation:**
- Structured prompts for consistent output
- Error handling for API failures
- Fallback to manual entry

## Security Architecture

### Authentication & Authorization

```
Request → Session Check → User Lookup → Permission Check → Route Handler
            ↓ (fail)         ↓ (fail)      ↓ (fail)
         Redirect to      403 Error     403 Error
           Login
```

**Security Measures:**
- Bcrypt password hashing (cost factor: 12)
- Session-based authentication
- CSRF protection on all forms
- Role-based access control (household owners vs members)

### Data Protection

- **SQL Injection**: Prevented via SQLAlchemy parameterized queries
- **XSS**: Jinja2 auto-escaping
- **CSRF**: Flask-WTF tokens
- **Password Storage**: Never stored in plain text
- **API Keys**: Environment variables, never committed

## Frontend Architecture

### JavaScript Organization

```javascript
// Modular structure with namespaces
ModalManager
  ├── open()
  ├── close()
  └── init()

RecipeManager
  ├── extractRecipe()
  ├── standardizeIngredients()
  ├── addManualIngredient()
  └── deleteIngredient()

UIUtils
  ├── showFlashMessage()
  ├── setButtonLoading()
  └── populateFormFields()
```

**Benefits:**
- No global namespace pollution
- Clear separation of concerns
- Easy to test and maintain
- Backward compatible with legacy code

### CSS Architecture

**Design System Approach:**
- CSS custom properties (variables) for theming
- Mobile-first responsive design
- Component-based styling
- Consistent spacing and typography scales

## Performance Optimizations

### Database

1. **Eager Loading**: Use `joinedload()` to prevent N+1 queries
2. **Indexing**: Indexes on foreign keys and frequently queried columns
3. **Connection Pooling**: SQLAlchemy manages connection pool
4. **Query Optimization**: Select only needed columns

### Caching

1. **Session Caching**: Store API responses in session
2. **Static Assets**: Browser caching headers
3. **Database Query Caching**: Planned with Redis

### Frontend

1. **Minification**: CSS/JS minification in production
2. **Lazy Loading**: Images and non-critical resources
3. **AJAX**: Partial page updates instead of full reloads

## Deployment Architecture

### Heroku Deployment

```
User Request → Heroku Router → Gunicorn → Flask App
                                              ↓
                                    PostgreSQL Database
                                              ↓
                                    External APIs
```

**Configuration:**
- Environment-based config (development/production)
- Automatic database URL detection
- Gunicorn WSGI server
- Process management via Procfile

### Environment Management

- `.env` for local development
- Heroku config vars for production
- Separate database connections per environment
- Feature flags for gradual rollouts

## Error Handling Strategy

### Layered Error Handling

1. **Service Layer**: Returns `(success, error_message)` tuples
2. **Route Layer**: Converts to HTTP responses and flash messages
3. **Frontend Layer**: Displays user-friendly messages
4. **Logging Layer**: Records errors for debugging

### Error Types

- **Validation Errors**: 400 with field-specific messages
- **Authentication Errors**: 401 with redirect to login
- **Authorization Errors**: 403 with access denied message
- **Not Found Errors**: 404 with helpful suggestions
- **Server Errors**: 500 with generic message (details logged)

## Testing Strategy (Planned)

### Unit Tests
- Service layer methods
- Utility functions
- Model methods

### Integration Tests
- Route handlers
- Database operations
- API integrations

### End-to-End Tests
- User workflows
- Multi-household scenarios
- Kroger integration

## Monitoring & Logging

### Logging Strategy

```python
logger.info()    # Normal operations
logger.warning() # Recoverable issues
logger.error()   # Errors requiring attention
logger.debug()   # Development debugging
```

**Log Levels by Environment:**
- Development: DEBUG
- Production: INFO

### Metrics (Planned)

- Request/response times
- API call success rates
- User activity patterns
- Error rates by type

## Scalability Considerations

### Current Capacity

- Single-server deployment
- PostgreSQL handles thousands of users
- Session-based state management

### Future Scaling

1. **Horizontal Scaling**: Multiple Heroku dynos
2. **Database**: Read replicas for queries
3. **Caching**: Redis for session and query caching
4. **CDN**: Static asset delivery
5. **Background Jobs**: Celery for async tasks
6. **Microservices**: Separate recipe scraping service

## Code Quality Standards

### Python Style

- PEP 8 compliance
- Type hints on all functions
- Docstrings (Google style)
- Maximum line length: 88 (Black formatter)

### JavaScript Style

- ES6+ features
- Consistent naming conventions
- JSDoc comments
- Modular organization

### Git Workflow

- Feature branches
- Descriptive commit messages
- Pull request reviews
- Semantic versioning

---

**Last Updated**: 2026-02-09
**Maintained By**: Elle White

