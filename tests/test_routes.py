"""
Integration tests for route handlers.

Tests HTTP endpoints including authentication, recipe management, and grocery lists.
"""

from datetime import date

import pytest

from models import MealPlanEntry


@pytest.mark.integration
class TestAuthRoutes:
    """Tests for authentication routes."""

    def test_login_page_loads(self, client):
        """Test that login page loads successfully."""
        response = client.get("/login")
        assert response.status_code == 200
        assert b"login" in response.data.lower() or b"sign in" in response.data.lower()

    def test_register_page_loads(self, client):
        """Test that registration page loads successfully."""
        response = client.get('/register')
        assert response.status_code == 200
        assert b'register' in response.data.lower() or b'sign up' in response.data.lower()

    def test_login_with_valid_credentials(self, client, sample_user):
        """Test logging in with valid credentials."""
        response = client.post(
            "/login",
            data={"username": "testuser", "password": "password123"},
            follow_redirects=True,
        )

        # Should redirect to home page after successful login
        assert response.status_code == 200

    def test_login_with_invalid_credentials(self, client):
        """Test logging in with invalid credentials."""
        response = client.post(
            "/login",
            data={"username": "nonexistent", "password": "wrongpassword"},
            follow_redirects=True,
        )

        # Should show error message
        assert response.status_code == 200
        assert b'invalid' in response.data.lower() or b'error' in response.data.lower()

    def test_logout(self, authenticated_client):
        """Test logging out."""
        response = authenticated_client.get("/logout", follow_redirects=True)
        assert response.status_code == 200


@pytest.mark.integration
class TestRecipeRoutes:
    """Tests for recipe management routes."""

    def test_home_page_requires_login(self, client):
        """Test that home page redirects to login when not authenticated."""
        response = client.get('/')
        # Should redirect to login
        assert response.status_code in [302, 401] or b'login' in response.data.lower()

    def test_home_page_loads_when_authenticated(
        self, authenticated_client, sample_household
    ):
        """Test that authenticated users can access home page."""
        with authenticated_client.session_transaction() as sess:
            sess["curr_household_id"] = sample_household.id

        response = authenticated_client.get('/')
        assert response.status_code == 200

    def test_add_recipe_page_loads(self, authenticated_client, sample_household):
        """Test that add recipe endpoint is reachable for authenticated users."""
        with authenticated_client.session_transaction() as sess:
            sess["curr_household_id"] = sample_household.id

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
        response = client.post("/grocery-list/create", data={"list_name": "Test List"})
        # Should redirect to login or return 401
        assert response.status_code in [302, 401]

    def test_grocery_list_api_requires_auth(self, client):
        """Test that grocery list API endpoints require authentication."""
        response = client.get('/api/grocery-list/1/state')
        # Should require authentication
        assert response.status_code in [302, 401] or b'login' in response.data.lower()

    def test_send_email_route_handles_missing_recipients(
        self, authenticated_client, sample_household, sample_grocery_list
    ):
        """Test grocery email route exists and redirects back to the email modal."""
        with authenticated_client.session_transaction() as sess:
            sess["curr_household_id"] = sample_household.id
            sess["curr_grocery_list_id"] = sample_grocery_list.id

        response = authenticated_client.post(
            "/send-email",
            data={"custom_email": "", "email_type": "list_and_recipes"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/#email-modal")

    def test_meal_plan_add_to_list_sets_selected_recipe_ids(
        self,
        authenticated_client,
        db_session,
        monkeypatch,
        sample_household,
        sample_grocery_list,
        sample_recipe,
        sample_user,
    ):
        """Meal-plan add-to-list should seed the same selected recipes used by the email modal."""
        meal_entry = MealPlanEntry(
            household_id=sample_household.id,
            recipe_id=sample_recipe.id,
            date=date.today(),
            meal_type="dinner",
        )
        db_session.add(meal_entry)
        db_session.commit()

        monkeypatch.setattr(
            "models.GroceryList.update_grocery_list",
            lambda *args, **kwargs: None,
        )

        with authenticated_client.session_transaction() as sess:
            sess["curr_household_id"] = sample_household.id
            sess["curr_grocery_list_id"] = sample_grocery_list.id
            sess["curr_user"] = sample_user.id

        response = authenticated_client.post(
            "/meal-plan/add-to-list",
            data={"week_offset": "0"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/")

        with authenticated_client.session_transaction() as sess:
            assert sess["selected_recipe_ids"] == [str(sample_recipe.id)]


@pytest.mark.integration
class TestUtilityRoutes:
    """Tests for utility routes and error handlers."""

    def test_404_handler(self, client):
        """Test that 404 errors are handled gracefully."""
        response = client.get("/nonexistent-page-12345")
        assert response.status_code == 404

    def test_health_check(self, client):
        """Test basic application health."""
        # Try accessing a public endpoint
        response = client.get('/login')
        assert response.status_code == 200
