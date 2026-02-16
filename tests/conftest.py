"""
Pytest configuration and fixtures for Auto-Cart tests.

This module provides shared fixtures for testing including:
- Test database setup/teardown
- Test client
- Sample data fixtures
"""

import os
import pytest
from app import app as flask_app
from models import db, User, Household, HouseholdMember, Recipe, GroceryList


@pytest.fixture(scope='session')
def app():
    """Create and configure a test application instance."""
    # Set testing environment variables
    os.environ['FLASK_ENV'] = 'testing'
    os.environ['SECRET_KEY'] = 'test-secret-key'
    os.environ['LOCAL_DATABASE_CONN'] = 'sqlite:///:memory:'
    
    # Reuse the application that has all routes registered.
    test_app = flask_app
    test_app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,  # Disable CSRF for testing
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    })
    
    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Create a test client for making requests."""
    return app.test_client()


@pytest.fixture(scope='function', autouse=True)
def ensure_tables(app):
    """Ensure database tables exist for every test."""
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()


@pytest.fixture(scope='function')
def db_session(app):
    """Create a new database session for a test."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield db.session
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(db_session):
    """Create a sample user for testing."""
    from models import bcrypt
    
    user = User(
        username='testuser',
        email='test@example.com',
        password=bcrypt.generate_password_hash('password123').decode('utf-8')
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_household(db_session, sample_user):
    """Create a sample household with the sample user as owner."""
    household = Household(name='Test Household')
    db_session.add(household)
    db_session.commit()
    
    # Add user as owner
    member = HouseholdMember(
        household_id=household.id,
        user_id=sample_user.id,
        role='owner'
    )
    db_session.add(member)
    db_session.commit()
    
    return household


@pytest.fixture
def sample_recipe(db_session, sample_household, sample_user):
    """Create a sample recipe for testing."""
    recipe = Recipe(
        household_id=sample_household.id,
        user_id=sample_user.id,
        name='Test Recipe',
        url='https://example.com/recipe',
        notes='Test recipe notes',
    )
    db_session.add(recipe)
    db_session.commit()
    return recipe


@pytest.fixture
def sample_grocery_list(db_session, sample_household, sample_user):
    """Create a sample grocery list for testing."""
    grocery_list = GroceryList(
        household_id=sample_household.id,
        user_id=sample_user.id,
        name='Test Grocery List',
        created_by_user_id=sample_user.id
    )
    db_session.add(grocery_list)
    db_session.commit()
    return grocery_list


@pytest.fixture
def authenticated_client(client, sample_user):
    """Create a client with an authenticated session."""
    with client.session_transaction() as session:
        session['curr_user'] = sample_user.id
    return client
