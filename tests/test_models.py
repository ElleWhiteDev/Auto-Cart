"""
Unit tests for database models.

Tests the core functionality of User, Household, Recipe, and GroceryList models.
"""

import pytest
from types import SimpleNamespace
import models
from models import User, Household, HouseholdMember, Recipe, RecipeIngredient, GroceryList, bcrypt


def _mock_claude(monkeypatch, reply):
    """Make every Claude call return `reply`."""
    monkeypatch.setattr("models._ask_claude", lambda *args, **kwargs: reply)


def _capture_claude_call(monkeypatch, reply):
    captured = {}

    def _fake_ask(system_prompt, user_content, json_schema=None):
        captured.update(
            system_prompt=system_prompt,
            user_content=user_content,
            json_schema=json_schema,
        )
        return reply

    monkeypatch.setattr("models._ask_claude", _fake_ask)
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
        _mock_claude(
            monkeypatch,
            '{"ingredients":[{"quantity":"14.5","measurement":"ounces","ingredient_name":"diced tomatoes"}]}'
        )

        parsed = Recipe.parse_ingredients("14.5 oz diced tomatoes")

        assert parsed == [
            {"quantity": "14.5", "measurement": "oz", "ingredient_name": "tomatoes"}
        ]

    def test_ask_claude_requests_json_schema_and_returns_text(self, monkeypatch):
        """_ask_claude should send the schema as structured output and return the text."""
        captured = {}

        def _fake_create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text=' {"ingredients": []} ')],
            )

        monkeypatch.setattr(models.ai_client.beta.messages, "create", _fake_create)

        reply = models._ask_claude("system", "user", json_schema={"type": "object"})

        assert reply == '{"ingredients": []}'
        assert captured["model"] == models.AI_MODEL
        assert captured["system"] == "system"
        assert captured["output_config"]["format"] == {
            "type": "json_schema",
            "schema": {"type": "object"},
        }

    def test_ask_claude_raises_on_refusal(self, monkeypatch):
        """A refusal should raise so callers use their non-AI fallback."""
        monkeypatch.setattr(
            models.ai_client.beta.messages,
            "create",
            lambda **kwargs: SimpleNamespace(stop_reason="refusal", content=[]),
        )

        with pytest.raises(RuntimeError):
            models._ask_claude("system", "user")

    def test_parse_ingredients_fallback_keeps_quantities(self, monkeypatch):
        """If the model call fails, simple parsing should keep explicit quantities."""

        def _fail(*args, **kwargs):
            raise RuntimeError("Claude unavailable")

        monkeypatch.setattr("models._ask_claude", _fail)

        assert Recipe.parse_ingredients("2 1/2 cups flour\n3 large eggs\nsalt") == [
            {"quantity": "2 1/2", "measurement": "cup", "ingredient_name": "flour"},
            {"quantity": "3", "measurement": "unit", "ingredient_name": "large eggs"},
            {"quantity": "1", "measurement": "unit", "ingredient_name": "salt"},
        ]

    def test_create_recipe_stores_parsed_ingredients(self, monkeypatch):
        """New recipes should store parsed quantities, not raw lines as names."""
        _mock_claude(
            monkeypatch,
            '{"ingredients":[{"quantity":"14.5","measurement":"oz","ingredient_name":"diced tomatoes"},'
            '{"quantity":"1/2","measurement":"cup","ingredient_name":"a very long ingredient name that exceeds the column"}]}'
        )

        recipe = Recipe.create_recipe(
            "1 (14.5 oz) can diced tomatoes\n1/2 cup something", None, 1, "Soup", None
        )

        assert [
            (i.quantity, i.measurement, i.ingredient_name)
            for i in recipe.recipe_ingredients
        ] == [
            (14.5, "oz", "tomatoes"),
            (0.5, "cup", "a very long ingredient name that exceeds"),
        ]

    def test_clean_ingredients_prompt_mentions_line_order_and_no_invention(
        self, monkeypatch
    ):
        """Cleaning prompt should emphasize stable line cleanup without hallucination."""
        captured = _capture_claude_call(monkeypatch, "1/2 cup sugar")

        Recipe.clean_ingredients_with_ai("½ cup sugar")

        system_prompt = captured["system_prompt"]
        assert (
            "Preserve the original ingredient order of retained lines." in system_prompt
        )
        assert (
            "Never invent missing ingredients, quantities, or units." in system_prompt
        )
        assert "Remove non-ingredient noise" in system_prompt

    def test_parse_prompt_mentions_json_contract_and_prep_removal(self, monkeypatch):
        """Parsing prompt should enforce strict JSON and shopping-safe normalization."""
        captured = _capture_claude_call(
            monkeypatch,
            '{"ingredients":[{"quantity":"1","measurement":"cup","ingredient_name":"yellow onion"}]}',
        )

        Recipe.parse_ingredients("1 cup yellow onion, diced")

        system_prompt = captured["system_prompt"]
        assert '"ingredients" array' in system_prompt
        assert captured["json_schema"] is models._PARSED_INGREDIENTS_SCHEMA
        assert "Remove prep-only descriptors wherever they appear" in system_prompt
        assert (
            "Never merge, deduplicate, summarize, or omit any meaningful ingredient line."
            in system_prompt
        )

    def test_parse_ingredients_strips_prep_but_keeps_variant(self, monkeypatch):
        """Post-processing should keep shoppable variants while removing prep-only wording."""
        _mock_claude(
            monkeypatch,
            '{"ingredients":[{"quantity":"1","measurement":"cup","ingredient_name":"yellow onion diced"}]}'
        )

        parsed = Recipe.parse_ingredients("1 cup yellow onion, diced")

        assert parsed == [
            {"quantity": "1", "measurement": "cup", "ingredient_name": "yellow onion"}
        ]

    def test_parse_ingredients_removes_note_only_phrases(self, monkeypatch):
        """Structured output should drop non-purchase notes while keeping the ingredient."""
        _mock_claude(
            monkeypatch,
            '{"ingredients":[{"quantity":"2","measurement":"tbsp","ingredient_name":"parsley divided"}]}'
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
        _mock_claude(monkeypatch, "1 unit chopped onion\n1 unit minced onion")

        consolidated = GroceryList.consolidate_ingredients_with_ai(
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
        _mock_claude(monkeypatch, "1 lb chicken breast\n1 lb chicken thighs")

        consolidated = GroceryList.consolidate_ingredients_with_ai(
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
        _mock_claude(monkeypatch, "14.5 oz diced tomatoes\n1 unit tomatoes")

        consolidated = GroceryList.consolidate_ingredients_with_ai(
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
        _mock_claude(monkeypatch, "1 unit tomatoes\n1 unit tomato sauce")

        consolidated = GroceryList.consolidate_ingredients_with_ai(
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
        captured = _capture_claude_call(monkeypatch, "1 unit onion")

        GroceryList.consolidate_ingredients_with_ai(
            [{"quantity": "1", "measurement": "unit", "ingredient_name": "onion"}]
        )

        system_prompt = captured["system_prompt"]
        assert (
            "If there is any reasonable doubt, keep the items separate."
            in system_prompt
        )
        assert "Preserve input order based on the first retained line." in system_prompt
        assert "Never invent new ingredients or omit non-water ingredients." in system_prompt

    def test_consolidate_unit_line_adds_once_to_repeated_real_unit_lines(
        self, monkeypatch
    ):
        """A "unit" line folds into the real measurement once, not once per line."""
        _mock_claude(
            monkeypatch,
            "1 lb ground beef\n1 lb ground beef\n1 unit ground beef"
        )

        consolidated = GroceryList.consolidate_ingredients_with_ai(
            [{"quantity": "1", "measurement": "lb", "ingredient_name": "ground beef"}]
        )

        assert consolidated == [
            {"quantity": "3", "measurement": "lb", "ingredient_name": "ground beef"}
        ]

    def test_consolidate_keeps_unit_line_when_real_units_are_ambiguous(
        self, monkeypatch
    ):
        """A "unit" line is kept rather than dropped when it can't be folded."""
        _mock_claude(
            monkeypatch,
            "1 unit butter\n1 tbsp butter\n1 cup butter"
        )

        consolidated = GroceryList.consolidate_ingredients_with_ai(
            [{"quantity": "1", "measurement": "unit", "ingredient_name": "butter"}]
        )

        assert consolidated == [
            {"quantity": "1", "measurement": "unit", "ingredient_name": "butter"},
            {"quantity": "1", "measurement": "tbsp", "ingredient_name": "butter"},
            {"quantity": "1", "measurement": "cup", "ingredient_name": "butter"},
        ]

    def test_consolidate_unit_line_counts_as_known_package_size(self, monkeypatch):
        """Any ingredient with one known package size treats a unit as one package."""
        _mock_claude(monkeypatch, "15 oz black beans\n1 unit black beans")

        consolidated = GroceryList.consolidate_ingredients_with_ai(
            [{"quantity": "15", "measurement": "oz", "ingredient_name": "black beans"}]
        )

        assert consolidated == [
            {"quantity": "30", "measurement": "oz", "ingredient_name": "black beans"}
        ]

    def test_consolidate_sums_mixed_number_quantities(self, monkeypatch):
        """Mixed numbers like "2 1/2" from the model are summed, not dropped."""
        _mock_claude(monkeypatch, "2 1/2 cup flour\n1 cup flour")

        consolidated = GroceryList.consolidate_ingredients_with_ai(
            [{"quantity": "1", "measurement": "cup", "ingredient_name": "flour"}]
        )

        assert consolidated == [
            {"quantity": "3.5", "measurement": "cup", "ingredient_name": "flour"}
        ]
