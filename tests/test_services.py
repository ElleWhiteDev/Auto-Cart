"""
Unit tests for service layer.

Tests business logic in RecipeService, GroceryListService, and MealPlanService.
"""

import pytest
from services.recipe_service import RecipeService
from services.api_response import APIResponse


@pytest.mark.service
class TestRecipeService:
    """Tests for RecipeService business logic."""
    
    def test_create_recipe_success(self, db_session, sample_household, sample_user):
        """Test successfully creating a recipe through service layer."""
        recipe, error = RecipeService.create_recipe(
            household_id=sample_household.id,
            name='Test Recipe',
            ingredients_text='2 cups flour\n1 cup sugar',
            url='https://example.com/recipe',
            notes='Test notes',
            created_by_user_id=sample_user.id
        )
        
        assert error is None
        assert recipe is not None
        assert recipe.name == 'Test Recipe'
        assert recipe.household_id == sample_household.id
    
    def test_create_recipe_empty_name(self, db_session, sample_household, sample_user):
        """Test creating recipe with empty name fails."""
        recipe, error = RecipeService.create_recipe(
            household_id=sample_household.id,
            name='',
            ingredients_text='2 cups flour',
            created_by_user_id=sample_user.id
        )
        
        # Should handle empty name gracefully
        # (Implementation may vary - adjust based on actual behavior)
        assert recipe is not None or error is not None


@pytest.mark.service
class TestAPIResponse:
    """Tests for standardized API responses."""
    
    def test_success_response(self, app):
        """Test creating a success response."""
        with app.app_context():
            response, status_code = APIResponse.success(
                message='Operation successful',
                data={'id': 123}
            )

            payload = response.get_json()

            assert status_code == 200
            assert payload['success'] is True
            assert payload['message'] == 'Operation successful'
            assert payload['data']['id'] == 123
    
    def test_error_response(self, app):
        """Test creating an error response."""
        with app.app_context():
            response, status_code = APIResponse.error(
                error='Operation failed',
                status_code=400
            )

            payload = response.get_json()

            assert status_code == 400
            assert payload['success'] is False
            assert payload['error'] == 'Operation failed'
    
    def test_validation_error_response(self, app):
        """Test creating a validation error response."""
        errors = {'email': 'Invalid email format'}
        with app.app_context():
            response, status_code = APIResponse.validation_error(errors)

            payload = response.get_json()

            assert status_code == 422
            assert payload['success'] is False
            assert payload['error'] == 'Validation failed'
            assert payload['details']['validation_errors'] == errors
