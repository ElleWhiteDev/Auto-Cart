"""
Integration tests for route handlers.

Tests HTTP endpoints including authentication, recipe management, and grocery lists.
"""

import pytest


@pytest.mark.integration
class TestAuthRoutes:
    """Tests for authentication routes."""
    
    def test_login_page_loads(self, client):
        """Test that login page loads successfully."""
        response = client.get('/login')
        assert response.status_code == 200
        assert b'login' in response.data.lower() or b'sign in' in response.data.lower()
    
    def test_register_page_loads(self, client):
        """Test that registration page loads successfully."""
        response = client.get('/register')
        assert response.status_code == 200
        assert b'register' in response.data.lower() or b'sign up' in response.data.lower()
    
    def test_login_with_valid_credentials(self, client, sample_user):
        """Test logging in with valid credentials."""
        response = client.post('/login', data={
            'username': 'testuser',
            'password': 'password123'
        }, follow_redirects=True)
        
        # Should redirect to home page after successful login
        assert response.status_code == 200
    
    def test_login_with_invalid_credentials(self, client):
        """Test logging in with invalid credentials."""
        response = client.post('/login', data={
            'username': 'nonexistent',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        
        # Should show error message
        assert response.status_code == 200
        assert b'invalid' in response.data.lower() or b'error' in response.data.lower()
    
    def test_logout(self, authenticated_client):
        """Test logging out."""
        response = authenticated_client.get('/logout', follow_redirects=True)
        assert response.status_code == 200


@pytest.mark.integration
class TestRecipeRoutes:
    """Tests for recipe management routes."""
    
    def test_home_page_requires_login(self, client):
        """Test that home page redirects to login when not authenticated."""
        response = client.get('/')
        # Should redirect to login
        assert response.status_code in [302, 401] or b'login' in response.data.lower()
    
    def test_home_page_loads_when_authenticated(self, authenticated_client, sample_household):
        """Test that authenticated users can access home page."""
        with authenticated_client.session_transaction() as sess:
            sess['curr_household_id'] = sample_household.id
        
        response = authenticated_client.get('/')
        assert response.status_code == 200
    
    def test_add_recipe_page_loads(self, authenticated_client, sample_household):
        """Test that add recipe endpoint is reachable for authenticated users."""
        with authenticated_client.session_transaction() as sess:
            sess['curr_household_id'] = sample_household.id
        
        response = authenticated_client.post('/add-recipe', data={
            'name': 'Test recipe',
            'ingredients_text': '1 cup flour',
            'url': '',
            'notes': ''
        })
        # Endpoint may redirect after processing form submission
        assert response.status_code in [200, 302]


@pytest.mark.integration
class TestGroceryListRoutes:
    """Tests for grocery list routes."""
    
    def test_create_grocery_list_requires_auth(self, client):
        """Test that creating grocery list requires authentication."""
        response = client.post('/grocery-list/create', data={
            'list_name': 'Test List'
        })
        # Should redirect to login or return 401
        assert response.status_code in [302, 401]
    
    def test_grocery_list_api_requires_auth(self, client):
        """Test that grocery list API endpoints require authentication."""
        response = client.get('/api/grocery-list/1/state')
        # Should require authentication
        assert response.status_code in [302, 401] or b'login' in response.data.lower()


@pytest.mark.integration
class TestUtilityRoutes:
    """Tests for utility routes and error handlers."""
    
    def test_404_handler(self, client):
        """Test that 404 errors are handled gracefully."""
        response = client.get('/nonexistent-page-12345')
        assert response.status_code == 404
    
    def test_health_check(self, client):
        """Test basic application health."""
        # Try accessing a public endpoint
        response = client.get('/login')
        assert response.status_code == 200
