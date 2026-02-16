"""
Unit tests for database models.

Tests the core functionality of User, Household, Recipe, and GroceryList models.
"""

import pytest
from models import User, Household, HouseholdMember, Recipe, RecipeIngredient, GroceryList, bcrypt


@pytest.mark.unit
class TestUserModel:
    """Tests for the User model."""
    
    def test_user_creation(self, db_session):
        """Test creating a new user."""
        user = User(
            username='newuser',
            email='newuser@example.com',
            password=bcrypt.generate_password_hash('password').decode('utf-8')
        )
        db_session.add(user)
        db_session.commit()
        
        assert user.id is not None
        assert user.username == 'newuser'
        assert user.email == 'newuser@example.com'
    
    def test_user_password_hashing(self, db_session):
        """Test that passwords are properly hashed."""
        password = 'mysecretpassword'
        user = User(
            username='testuser',
            email='test@example.com',
            password=bcrypt.generate_password_hash(password).decode('utf-8')
        )
        db_session.add(user)
        db_session.commit()
        
        # Password should be hashed, not plain text
        assert user.password != password
        # Should be able to verify password
        assert bcrypt.check_password_hash(user.password, password)
    
    def test_user_repr(self, sample_user):
        """Test user string representation."""
        repr_str = repr(sample_user)
        assert 'User' in repr_str
        assert str(sample_user.id) in repr_str
        assert sample_user.username in repr_str


@pytest.mark.unit
class TestHouseholdModel:
    """Tests for the Household model."""
    
    def test_household_creation(self, db_session):
        """Test creating a new household."""
        household = Household(name='My Family')
        db_session.add(household)
        db_session.commit()
        
        assert household.id is not None
        assert household.name == 'My Family'
        assert household.created_at is not None
    
    def test_household_members_relationship(self, sample_household, sample_user):
        """Test household members relationship."""
        assert len(sample_household.members) > 0
        assert sample_household.members[0].user_id == sample_user.id
    
    def test_is_user_owner(self, sample_household, sample_user):
        """Test checking if user is household owner."""
        assert sample_household.is_user_owner(sample_user.id) is True
    
    def test_is_user_member(self, sample_household, sample_user):
        """Test checking if user is household member."""
        assert sample_household.is_user_member(sample_user.id) is True
    
    def test_get_owners(self, sample_household):
        """Test getting household owners."""
        owners = sample_household.get_owners()
        assert len(owners) > 0
        assert owners[0].role == 'owner'


@pytest.mark.unit
class TestRecipeModel:
    """Tests for the Recipe model."""
    
    def test_recipe_creation(self, db_session, sample_household, sample_user):
        """Test creating a new recipe."""
        recipe = Recipe(
            household_id=sample_household.id,
            user_id=sample_user.id,
            name='Chocolate Cake',
            url='https://example.com/cake',
            notes='Delicious cake recipe',
        )
        db_session.add(recipe)
        db_session.commit()
        
        assert recipe.id is not None
        assert recipe.name == 'Chocolate Cake'
        assert recipe.household_id == sample_household.id
    
    def test_recipe_household_relationship(self, sample_recipe, sample_household):
        """Test recipe belongs to household."""
        assert sample_recipe.household_id == sample_household.id
        assert sample_recipe in sample_household.recipes
    
    def test_recipe_ingredients_relationship(self, db_session, sample_recipe):
        """Test recipe ingredients relationship."""
        ingredient = RecipeIngredient(
            recipe_id=sample_recipe.id,
            quantity=2.0,
            measurement='cups',
            ingredient_name='flour'
        )
        db_session.add(ingredient)
        db_session.commit()
        
        assert len(sample_recipe.recipe_ingredients) == 1
        assert sample_recipe.recipe_ingredients[0].ingredient_name == 'flour'


@pytest.mark.unit
class TestGroceryListModel:
    """Tests for the GroceryList model."""
    
    def test_grocery_list_creation(self, db_session, sample_household, sample_user):
        """Test creating a new grocery list."""
        grocery_list = GroceryList(
            household_id=sample_household.id,
            user_id=sample_user.id,
            name='Weekly Shopping',
            created_by_user_id=sample_user.id
        )
        db_session.add(grocery_list)
        db_session.commit()
        
        assert grocery_list.id is not None
        assert grocery_list.name == 'Weekly Shopping'
        assert grocery_list.household_id == sample_household.id
    
    def test_grocery_list_household_relationship(self, sample_grocery_list, sample_household):
        """Test grocery list belongs to household."""
        assert sample_grocery_list.household_id == sample_household.id
        assert sample_grocery_list in sample_household.grocery_lists
