"""
Unit tests for database models.

Tests the core functionality of User, Household, Recipe, and GroceryList models.
"""

import pytest
from types import SimpleNamespace
from models import User, Household, HouseholdMember, Recipe, RecipeIngredient, GroceryList, bcrypt


def _mock_openai_response(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _capture_openai_call(monkeypatch, response_content):
    captured = {}

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return _mock_openai_response(response_content)

    monkeypatch.setattr(
        "models.openai_client.chat.completions.create",
        _fake_create,
    )
    return captured


@pytest.mark.unit
class TestUserModel:
    """Tests for the User model."""

    def test_user_creation(self, db_session):
        """Test creating a new user."""
        user = User(
            username="newuser",
            email="newuser@example.com",
            password=bcrypt.generate_password_hash("password").decode("utf-8"),
        )
        db_session.add(user)
        db_session.commit()

        assert user.id is not None
        assert user.username == 'newuser'
        assert user.email == 'newuser@example.com'

    def test_user_password_hashing(self, db_session):
        """Test that passwords are properly hashed."""
        password = "mysecretpassword"
        user = User(
            username="testuser",
            email="test@example.com",
            password=bcrypt.generate_password_hash(password).decode("utf-8"),
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
        assert "User" in repr_str
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
        assert household.name == "My Family"
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
        assert owners[0].role == "owner"


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
        assert recipe.name == "Chocolate Cake"
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
            measurement="cups",
            ingredient_name="flour",
        )
        db_session.add(ingredient)
        db_session.commit()

        assert len(sample_recipe.recipe_ingredients) == 1
        assert sample_recipe.recipe_ingredients[0].ingredient_name == 'flour'

    def test_parse_ingredients_normalizes_oz_tomatoes(self, monkeypatch):
        """Prep descriptors should be removed from parsed tomato ingredients."""
        response = _mock_openai_response(
            '[{"quantity":"14.5","measurement":"ounces","ingredient_name":"diced tomatoes"}]'
        )

        monkeypatch.setattr(
            "models.openai_client.chat.completions.create",
            lambda **kwargs: response,
        )

        parsed = Recipe.parse_ingredients("14.5 oz diced tomatoes")

        assert parsed == [
            {"quantity": "14.5", "measurement": "oz", "ingredient_name": "tomatoes"}
        ]

    def test_clean_ingredients_prompt_mentions_line_order_and_no_invention(
        self, monkeypatch
    ):
        """Cleaning prompt should emphasize stable line cleanup without hallucination."""
        captured = _capture_openai_call(monkeypatch, "1/2 cup sugar")

        Recipe.clean_ingredients_with_openai("½ cup sugar")

        system_prompt = captured["messages"][0]["content"]
        assert (
            "Preserve the original ingredient order of retained lines." in system_prompt
        )
        assert (
            "Never invent missing ingredients, quantities, or units." in system_prompt
        )
        assert "Remove non-ingredient noise" in system_prompt

    def test_parse_prompt_mentions_json_contract_and_prep_removal(self, monkeypatch):
        """Parsing prompt should enforce strict JSON and shopping-safe normalization."""
        captured = _capture_openai_call(
            monkeypatch,
            '[{"quantity":"1","measurement":"cup","ingredient_name":"yellow onion"}]',
        )

        Recipe.parse_ingredients("1 cup yellow onion, diced")

        system_prompt = captured["messages"][0]["content"]
        assert "Return ONLY a valid JSON array." in system_prompt
        assert "Remove prep-only descriptors wherever they appear" in system_prompt
        assert (
            "Never merge, deduplicate, summarize, or omit any meaningful ingredient line."
            in system_prompt
        )

    def test_parse_ingredients_strips_prep_but_keeps_variant(self, monkeypatch):
        """Post-processing should keep shoppable variants while removing prep-only wording."""
        response = _mock_openai_response(
            '[{"quantity":"1","measurement":"cup","ingredient_name":"yellow onion diced"}]'
        )

        monkeypatch.setattr(
            "models.openai_client.chat.completions.create",
            lambda **kwargs: response,
        )

        parsed = Recipe.parse_ingredients("1 cup yellow onion, diced")

        assert parsed == [
            {"quantity": "1", "measurement": "cup", "ingredient_name": "yellow onion"}
        ]

    def test_parse_ingredients_removes_note_only_phrases(self, monkeypatch):
        """Structured output should drop non-purchase notes while keeping the ingredient."""
        response = _mock_openai_response(
            '[{"quantity":"2","measurement":"tbsp","ingredient_name":"parsley divided"}]'
        )

        monkeypatch.setattr(
            "models.openai_client.chat.completions.create",
            lambda **kwargs: response,
        )

        parsed = Recipe.parse_ingredients("2 tbsp parsley, divided")

        assert parsed == [
            {"quantity": "2", "measurement": "tbsp", "ingredient_name": "parsley"}
        ]


@pytest.mark.unit
class TestGroceryListModel:
    """Tests for the GroceryList model."""

    def test_grocery_list_creation(self, db_session, sample_household, sample_user):
        """Test creating a new pantry list."""
        grocery_list = GroceryList(
            household_id=sample_household.id,
            user_id=sample_user.id,
            name="Weekly Shopping",
            created_by_user_id=sample_user.id,
        )
        db_session.add(grocery_list)
        db_session.commit()

        assert grocery_list.id is not None
        assert grocery_list.name == 'Weekly Shopping'
        assert grocery_list.household_id == sample_household.id

    def test_grocery_list_household_relationship(self, sample_grocery_list, sample_household):
        """Test pantry list belongs to household."""
        assert sample_grocery_list.household_id == sample_household.id
        assert sample_grocery_list in sample_household.grocery_lists

    def test_consolidate_merges_prep_variants(self, monkeypatch):
        """Prep-only wording differences should collapse into one grocery line."""
        response = _mock_openai_response("1 unit chopped onion\n1 unit minced onion")

        monkeypatch.setattr(
            "models.openai_client.chat.completions.create",
            lambda **kwargs: response,
        )

        consolidated = GroceryList.consolidate_ingredients_with_openai(
            [
                {
                    "quantity": "1",
                    "measurement": "unit",
                    "ingredient_name": "chopped onion",
                },
                {
                    "quantity": "1",
                    "measurement": "unit",
                    "ingredient_name": "minced onion",
                },
            ]
        )

        assert consolidated == [
            {"quantity": "2", "measurement": "unit", "ingredient_name": "onion"}
        ]

    def test_consolidate_keeps_chicken_cuts_separate(self, monkeypatch):
        """Purchase-critical chicken cut differences should remain distinct."""
        response = _mock_openai_response("1 lb chicken breast\n1 lb chicken thighs")

        monkeypatch.setattr(
            "models.openai_client.chat.completions.create",
            lambda **kwargs: response,
        )

        consolidated = GroceryList.consolidate_ingredients_with_openai(
            [
                {
                    "quantity": "1",
                    "measurement": "lb",
                    "ingredient_name": "chicken breast",
                },
                {
                    "quantity": "1",
                    "measurement": "lb",
                    "ingredient_name": "chicken thighs",
                },
            ]
        )

        assert consolidated == [
            {"quantity": "1", "measurement": "lb", "ingredient_name": "chicken breast"},
            {"quantity": "1", "measurement": "lb", "ingredient_name": "chicken thigh"},
        ]

    def test_consolidate_combines_weighted_and_plain_tomatoes(self, monkeypatch):
        """Explicitly sized canned tomatoes should absorb plain unit tomato lines."""
        response = _mock_openai_response("14.5 oz diced tomatoes\n1 unit tomatoes")

        monkeypatch.setattr(
            "models.openai_client.chat.completions.create",
            lambda **kwargs: response,
        )

        consolidated = GroceryList.consolidate_ingredients_with_openai(
            [
                {
                    "quantity": "14.5",
                    "measurement": "oz",
                    "ingredient_name": "diced tomatoes",
                },
                {"quantity": "1", "measurement": "unit", "ingredient_name": "tomatoes"},
            ]
        )

        assert consolidated == [
            {"quantity": "29", "measurement": "oz", "ingredient_name": "tomatoes"}
        ]

    def test_consolidate_keeps_tomatoes_and_sauce_separate(self, monkeypatch):
        """Tomatoes should not collapse into tomato sauce products."""
        response = _mock_openai_response("1 unit tomatoes\n1 unit tomato sauce")

        monkeypatch.setattr(
            "models.openai_client.chat.completions.create",
            lambda **kwargs: response,
        )

        consolidated = GroceryList.consolidate_ingredients_with_openai(
            [
                {"quantity": "1", "measurement": "unit", "ingredient_name": "tomatoes"},
                {
                    "quantity": "1",
                    "measurement": "unit",
                    "ingredient_name": "tomato sauce",
                },
            ]
        )

        assert consolidated == [
            {"quantity": "1", "measurement": "unit", "ingredient_name": "tomatoes"},
            {"quantity": "1", "measurement": "unit", "ingredient_name": "tomato sauce"},
        ]

    def test_consolidate_prompt_mentions_conservative_merging_and_order(
        self, monkeypatch
    ):
        """Consolidation prompt should prefer safe merges and stable ordering."""
        captured = _capture_openai_call(monkeypatch, "1 unit onion")

        GroceryList.consolidate_ingredients_with_openai(
            [{"quantity": "1", "measurement": "unit", "ingredient_name": "onion"}]
        )

        system_prompt = captured["messages"][0]["content"]
        assert (
            "If there is any reasonable doubt, keep the items separate."
            in system_prompt
        )
        assert "Preserve input order based on the first retained line." in system_prompt
        assert (
            "Never omit a non-water ingredient unless it has been merged"
            in system_prompt
        )
