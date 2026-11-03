"""Tests for the meal plan similar-recipes matcher."""

from types import SimpleNamespace

import pytest

from models import MealPlanEntry, PantryStaple, Recipe, RecipeIngredient
from routes.meal_plan import (
    _CANONICAL_STAPLES,
    _ingredient_match_score,
    _is_pantry_staple,
    _normalize_ingredient_name,
    _score_recipe_match,
)
from utils import get_est_date


def _recipe(*names, recipe_id=1):
    ingredients = [SimpleNamespace(ingredient_name=n, quantity=None, measurement=None) for n in names]
    return SimpleNamespace(id=recipe_id, name="Recipe", recipe_ingredients=ingredients)


class TestNormalizeIngredientName:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("2 cups chopped Yellow Onions", "yellow onion"),
            ("Tomatoes", "tomato"),
            ("1 lb boneless, skinless chicken thighs", "chicken thigh"),
            ("salt and pepper to taste", "salt pepper"),
            ("fresh cilantro", "fresh cilantro"),
            ("2 large", "large"),
        ],
    )
    def test_normalizes(self, raw, expected):
        assert _normalize_ingredient_name(raw) == expected


class TestIsPantryStaple:
    @pytest.mark.parametrize(
        "name",
        ["salt", "kosher salt", "olive oil", "salt and pepper to taste", "2 tbsp unsalted butter", "dried basil"],
    )
    def test_staples(self, name):
        assert _is_pantry_staple(_normalize_ingredient_name(name))

    @pytest.mark.parametrize(
        "name",
        ["bell peppers", "jalapeno pepper", "coconut milk", "buttermilk", "peanut butter",
         "sugar snap peas", "fresh basil", "cilantro", "garlic salt"],
    )
    def test_real_ingredients_are_not_staples(self, name):
        assert not _is_pantry_staple(_normalize_ingredient_name(name))

    def test_household_staples_are_respected(self):
        staples = _CANONICAL_STAPLES | {"garlic"}
        assert _is_pantry_staple("garlic", staples)
        assert not _is_pantry_staple("garlic")


class TestIngredientMatchScore:
    def test_exact(self):
        assert _ingredient_match_score("tomato", {"tomato"}) == 1.0

    def test_more_specific_name_is_full_match(self):
        assert _ingredient_match_score("onion", {"yellow onion"}) == 1.0
        assert _ingredient_match_score("yellow onion", {"onion"}) == 1.0

    def test_different_cut_is_partial(self):
        assert _ingredient_match_score("chicken breast", {"chicken thigh"}) == 0.5

    def test_shared_modifier_only_is_no_match(self):
        assert _ingredient_match_score("green onion", {"green bean"}) == 0.0

    def test_unrelated(self):
        assert _ingredient_match_score("rice", {"tomato", "onion"}) == 0.0


class TestScoreRecipeMatch:
    def test_coverage_ignores_staples_and_counts_new_items(self):
        week = {"tomato", "yellow onion", "fresh cilantro"}
        match = _score_recipe_match(_recipe("2 tomatoes", "onion", "salt", "black beans"), week)
        assert match["match_percentage"] == 67
        assert match["matched_count"] == 2
        assert match["new_item_count"] == 1
        assert [i["matched"] for i in match["ingredients"]] == [True, True, False, False]

    def test_single_shared_ingredient_is_not_enough(self):
        assert _score_recipe_match(_recipe("onion", "pasta"), {"onion"}) is None

    def test_partial_matches_count_half(self):
        match = _score_recipe_match(_recipe("chicken breast", "tomato"), {"chicken thigh", "tomato"})
        assert match["match_percentage"] == 75
        assert match["new_item_count"] == 1
        assert match["ingredients"][0]["partial"] is True

    def test_below_threshold(self):
        week = {"onion", "tomato"}
        recipe = _recipe("onion", "tomato", "a", "b", "c", "d", "e", "f", "g")
        assert _score_recipe_match(recipe, week) is None


class TestFindSimilarRecipesRoute:
    def _add_recipe(self, db_session, household, user, name, ingredients):
        recipe = Recipe(household_id=household.id, user_id=user.id, name=name)
        recipe.recipe_ingredients = [RecipeIngredient(ingredient_name=i) for i in ingredients]
        db_session.add(recipe)
        db_session.commit()
        return recipe

    def test_ranks_by_coverage_and_uses_household_staples(
        self, authenticated_client, db_session, sample_household, sample_user
    ):
        planned = self._add_recipe(
            db_session, sample_household, sample_user, "Tacos",
            ["ground beef", "tomatoes", "onion", "cilantro", "garlic"],
        )
        self._add_recipe(db_session, sample_household, sample_user, "Salsa", ["tomato", "onion", "cilantro"])
        self._add_recipe(db_session, sample_household, sample_user, "Chili", ["ground beef", "tomato", "kidney beans", "garlic"])
        self._add_recipe(db_session, sample_household, sample_user, "Garlic Bread", ["garlic", "baguette"])
        db_session.add(PantryStaple(household_id=sample_household.id, ingredient_name="garlic"))
        db_session.add(
            MealPlanEntry(household_id=sample_household.id, recipe_id=planned.id, date=get_est_date(), meal_type="dinner")
        )
        db_session.commit()

        response = authenticated_client.post("/meal-plan/similar-recipes", data={"week_offset": 0})

        data = response.get_json()
        assert data["success"] is True
        assert [r["name"] for r in data["matched_recipes"]] == ["Salsa", "Chili"]
        assert data["matched_recipes"][0]["new_item_count"] == 0
        assert data["matched_recipes"][1]["new_item_count"] == 1
        # Garlic is a household staple, so Chili is scored on 3 ingredients, not 4.
        assert data["matched_recipes"][1]["match_percentage"] == 67


def test_format_quantity():
    from utils import format_quantity

    assert format_quantity(10.0) == "10"
    assert format_quantity(21.5) == "21.5"
    assert format_quantity(21.05) == "21.05"
    assert format_quantity(1 / 3) == "0.33"
    assert format_quantity(None) == ""
