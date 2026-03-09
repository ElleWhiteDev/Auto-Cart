"""Integration tests for route handlers.

Tests HTTP endpoints including authentication, recipe management, and grocery lists.
"""

from datetime import date, datetime, timezone

import pytest

from models import (
    MealPlanEntry,
    MealPlanChange,
    RecipeIngredient,
    GroceryListItem,
    HouseholdMember,
    User,
)


def _alexa_request_payload(request_body, access_token=None):
    """Build a valid Alexa-style request payload for tests."""

    session = {
        "new": False,
        "sessionId": "SessionId.test-session",
        "application": {"applicationId": "amzn1.ask.skill.test-skill"},
        "user": {},
    }
    if access_token:
        session["user"]["accessToken"] = access_token

    payload = {
        "version": "1.0",
        "session": session,
        "request": {
            **request_body,
            "requestId": "EdwRequestId.test-request",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }
    return payload


@pytest.mark.integration
class TestAuthRoutes:
    """Tests for authentication routes."""

    @pytest.mark.parametrize(
        "path",
        [
            "/alexa/authorize",
            "/api/alexa/authorize",
            "/api/alex/authorize",
        ],
    )
    def test_alexa_authorize_paths_load_login_page(self, client, path):
        """Test Alexa account linking aliases all serve the login page."""
        response = client.get(
            f"{path}?redirect_uri=https://example.com/cb&state=test&client_id=autocart-alexa"
        )

        assert response.status_code == 200
        assert b"login" in response.data.lower() or b"sign in" in response.data.lower()

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
class TestAlexaRoutes:
    """Tests for Alexa webhook and fulfillment routing."""

    def test_alexa_webhook_launch_request_returns_welcome(self, client):
        response = client.post(
            "/api/alexa/webhook",
            json=_alexa_request_payload({"type": "LaunchRequest"}),
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "Welcome to Auto-Cart" in data["response"]["outputSpeech"]["text"]
        assert data["response"]["shouldEndSession"] is False

    def test_alexa_webhook_add_item_intent_adds_item_to_list(
        self,
        client,
        db_session,
        monkeypatch,
        sample_user,
        sample_grocery_list,
    ):
        sample_user.alexa_access_token = "test-alexa-token"
        sample_user.alexa_default_grocery_list_id = sample_grocery_list.id
        db_session.commit()

        monkeypatch.setattr(
            "alexa_api.Recipe.parse_ingredients",
            lambda ingredient_text: [
                {
                    "quantity": "1",
                    "measurement": "unit",
                    "ingredient_name": "bananas",
                }
            ],
        )
        monkeypatch.setattr(
            "alexa_api.GroceryList.consolidate_ingredients_with_openai",
            lambda ingredients: ingredients,
        )

        response = client.post(
            "/api/alexa/webhook",
            json=_alexa_request_payload(
                {
                    "type": "IntentRequest",
                    "intent": {
                        "name": "AddItemIntent",
                        "slots": {
                            "item": {"name": "item", "value": "bananas"},
                        },
                    },
                },
                access_token=sample_user.alexa_access_token,
            ),
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "I've added bananas" in data["response"]["outputSpeech"]["text"]

        items = GroceryListItem.query.filter_by(
            grocery_list_id=sample_grocery_list.id,
            completed=False,
        ).all()
        assert len(items) == 1
        assert items[0].recipe_ingredient.ingredient_name == "bananas"

    def test_alexa_webhook_read_list_intent_reads_existing_items(
        self,
        client,
        db_session,
        sample_user,
        sample_grocery_list,
    ):
        sample_user.alexa_access_token = "test-alexa-token"
        sample_user.alexa_default_grocery_list_id = sample_grocery_list.id

        ingredient = RecipeIngredient(
            ingredient_name="milk",
            quantity=2.0,
            measurement="unit",
        )
        db_session.add(ingredient)
        db_session.flush()

        list_item = GroceryListItem(
            grocery_list_id=sample_grocery_list.id,
            recipe_ingredient_id=ingredient.id,
            added_by_user_id=sample_user.id,
            completed=False,
        )
        db_session.add(list_item)
        db_session.commit()

        response = client.post(
            "/api/alexa/webhook",
            json=_alexa_request_payload(
                {
                    "type": "IntentRequest",
                    "intent": {"name": "ReadListIntent", "slots": {}},
                },
                access_token=sample_user.alexa_access_token,
            ),
        )

        assert response.status_code == 200
        data = response.get_json()
        assert (
            "You have 1 item on your list" in data["response"]["outputSpeech"]["text"]
        )
        assert "milk" in data["response"]["outputSpeech"]["text"]

    def test_alexa_webhook_add_item_requires_linked_account(self, client):
        response = client.post(
            "/api/alexa/webhook",
            json=_alexa_request_payload(
                {
                    "type": "IntentRequest",
                    "intent": {
                        "name": "AddItemIntent",
                        "slots": {
                            "item": {"name": "item", "value": "bananas"},
                        },
                    },
                }
            ),
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["response"]["card"]["type"] == "LinkAccount"


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
class TestMealPlanRoutes:
    """Tests for meal plan routes."""

    def test_daily_summary_route_sends_pending_updates(
        self, client, db_session, monkeypatch, sample_household, sample_user
    ):
        """Daily summaries should process unemailed changes in changed_at order."""
        monkeypatch.setenv("CRON_SECRET_TOKEN", "test-cron-token")

        first_change = MealPlanChange(
            household_id=sample_household.id,
            change_type="added",
            meal_name="Pasta Night",
            meal_date=date.today(),
            meal_type="dinner",
            changed_by_user_id=sample_user.id,
            changed_at=datetime(2024, 1, 2, 18, 0, 0),
        )
        second_change = MealPlanChange(
            household_id=sample_household.id,
            change_type="updated",
            meal_name="Taco Tuesday",
            meal_date=date.today(),
            meal_type="lunch",
            changed_by_user_id=sample_user.id,
            changed_at=datetime(2024, 1, 2, 19, 0, 0),
            change_details="Moved to lunch",
        )
        db_session.add_all([first_change, second_change])
        db_session.commit()

        captured = {}

        def fake_send_summary_email(**kwargs):
            captured["recipient_email"] = kwargs["recipient_email"]
            captured["added_names"] = [
                change.meal_name for change in kwargs["added_changes"]
            ]
            captured["updated_names"] = [
                change.meal_name for change in kwargs["updated_changes"]
            ]

        monkeypatch.setattr(
            "routes.meal_plan._send_meal_plan_summary_email", fake_send_summary_email
        )

        response = client.post(
            "/meal-plan/send-daily-summaries",
            headers={"X-Cron-Token": "test-cron-token"},
        )

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["results"][0]["status"] == "success"
        assert payload["results"][0]["emails_sent"] == 1
        assert payload["results"][0]["changes_count"] == 2
        assert captured == {
            "recipient_email": sample_user.email,
            "added_names": ["Pasta Night"],
            "updated_names": ["Taco Tuesday"],
        }

        refreshed_changes = MealPlanChange.query.order_by(
            MealPlanChange.changed_at
        ).all()
        assert [change.emailed for change in refreshed_changes] == [True, True]


@pytest.mark.integration
class TestKrogerRoutes:
    """Tests for Kroger auth recovery and export summary routes."""

    def _add_grocery_list_item(
        self,
        db_session,
        grocery_list,
        ingredient_name,
        quantity=1,
        measurement="unit",
    ):
        """Create a grocery-list item for Kroger route tests."""
        ingredient = RecipeIngredient(
            ingredient_name=ingredient_name,
            quantity=quantity,
            measurement=measurement,
        )
        db_session.add(ingredient)
        db_session.flush()

        grocery_list_item = GroceryListItem(
            grocery_list_id=grocery_list.id,
            recipe_ingredient_id=ingredient.id,
        )
        db_session.add(grocery_list_item)
        db_session.commit()
        return grocery_list_item

    def _add_household_member(
        self, db_session, household, sample_user, username, email
    ):
        """Create a second household member for route tests."""
        household_user = User(
            username=username,
            email=email,
            password=sample_user.password,
        )
        db_session.add(household_user)
        db_session.flush()
        db_session.add(
            HouseholdMember(
                household_id=household.id,
                user_id=household_user.id,
                role="member",
            )
        )
        db_session.commit()
        return household_user

    def test_send_to_cart_with_expired_token_shows_reconnect_prompt(
        self,
        authenticated_client,
        db_session,
        monkeypatch,
        sample_household,
        sample_user,
    ):
        """Expired auth should preserve cart selections and guide the user to reconnect."""
        second_user = self._add_household_member(
            db_session,
            sample_household,
            sample_user,
            "housemate",
            "housemate@example.com",
        )
        sample_user.oauth_token = "expired-token"
        sample_user.refresh_token = "refresh-token"
        sample_household.kroger_user_id = sample_user.id
        db_session.commit()

        workflow = authenticated_client.application.config["kroger_workflow"]
        monkeypatch.setattr(workflow, "ensure_valid_token", lambda user: None)

        with authenticated_client.session_transaction() as sess:
            sess["household_id"] = sample_household.id
            sess["products_for_cart"] = [{"upc": "000111222333", "quantity": 1}]
            sess["skipped_ingredients"] = ["1 unit milk"]
            sess["location_id"] = "store-123"

        response = authenticated_client.get(
            f"/send-to-cart?confirmed=true&email_recipient_ids={second_user.id}&include_grocery_list=true",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Reconnect Kroger to finish sending your cart" in response.data
        assert b"Reconnect Kroger" in response.data
        assert (
            b"Your Kroger connection expired before we could send your cart"
            in response.data
        )

        with authenticated_client.session_transaction() as sess:
            assert sess["products_for_cart"] == [{"upc": "000111222333", "quantity": 1}]
            assert sess["skipped_ingredients"] == ["1 unit milk"]
            assert "confirmed=true" in sess["kroger_post_auth_redirect"]
            assert (
                f"email_recipient_ids={second_user.id}"
                in sess["kroger_post_auth_redirect"]
            )
            assert "include_grocery_list=true" in sess["kroger_post_auth_redirect"]
            assert sess["kroger_recovery_prompt"]["primary_url"].endswith(
                "/authenticate?resume=send-to-cart"
            )

    def test_authenticate_resume_keeps_cart_progress(
        self, authenticated_client, monkeypatch
    ):
        """Reconnect auth should not clear the in-progress Kroger cart state."""
        workflow = authenticated_client.application.config["kroger_workflow"]
        captured = {}

        def fake_handle_authentication(
            user, oauth_base_url, redirect_url, success_redirect_url=None
        ):
            captured["success_redirect_url"] = success_redirect_url
            return success_redirect_url

        monkeypatch.setattr(
            workflow, "handle_authentication", fake_handle_authentication
        )

        with authenticated_client.session_transaction() as sess:
            sess["products_for_cart"] = [{"upc": "000111222333", "quantity": 1}]
            sess["kroger_post_auth_redirect"] = "/send-to-cart?confirmed=true"

        response = authenticated_client.get(
            "/authenticate?resume=send-to-cart", follow_redirects=False
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/send-to-cart?confirmed=true")
        assert captured["success_redirect_url"] == "/send-to-cart?confirmed=true"

        with authenticated_client.session_transaction() as sess:
            assert sess["products_for_cart"] == [{"upc": "000111222333", "quantity": 1}]

    def test_callback_resumes_saved_send_to_cart_after_success(
        self, authenticated_client, monkeypatch
    ):
        """Successful Kroger callback should resume the saved cart flow."""
        workflow = authenticated_client.application.config["kroger_workflow"]
        monkeypatch.setattr(
            workflow,
            "handle_callback",
            lambda authorization_code, user, redirect_url: True,
        )

        with authenticated_client.session_transaction() as sess:
            sess["kroger_post_auth_redirect"] = "/send-to-cart?confirmed=true"
            sess["kroger_recovery_prompt"] = {
                "title": "Reconnect Kroger to finish sending your cart",
                "message": "Reconnect to continue.",
                "primary_label": "Reconnect Kroger",
                "primary_url": "/authenticate?resume=send-to-cart",
            }

        response = authenticated_client.get("/callback?code=test-code")

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/send-to-cart?confirmed=true")

        with authenticated_client.session_transaction() as sess:
            assert "kroger_post_auth_redirect" not in sess
            assert "kroger_recovery_prompt" not in sess

    def test_send_to_cart_shows_summary_even_without_skipped_items(
        self,
        authenticated_client,
        db_session,
        sample_household,
        sample_user,
        sample_grocery_list,
    ):
        """The export summary should still appear when nothing was skipped."""
        second_user = self._add_household_member(
            db_session,
            sample_household,
            sample_user,
            "housemate",
            "housemate@example.com",
        )

        with authenticated_client.session_transaction() as sess:
            sess["household_id"] = sample_household.id

        response = authenticated_client.get("/send-to-cart", follow_redirects=True)

        assert response.status_code == 200
        assert b"Kroger Export Summary" in response.data
        assert b"Continue to Kroger" in response.data
        assert b"Remove exported grocery list items after sending" in response.data
        assert b"Email selected household members" in response.data
        assert second_user.username.encode() in response.data
        assert second_user.email.encode() in response.data
        assert b"Include the grocery list in the email" in response.data

    def test_send_to_cart_emails_household_members_when_requested(
        self,
        authenticated_client,
        db_session,
        monkeypatch,
        sample_household,
        sample_user,
        sample_grocery_list,
    ):
        """Requesting household email notifications should trigger the Kroger email helper."""
        second_user = self._add_household_member(
            db_session,
            sample_household,
            sample_user,
            "familymember",
            "familymember@example.com",
        )
        self._add_grocery_list_item(db_session, sample_grocery_list, "milk")
        self._add_grocery_list_item(db_session, sample_grocery_list, "bread")

        sample_user.oauth_token = "valid-token"
        sample_user.refresh_token = "refresh-token"
        sample_household.kroger_user_id = sample_user.id
        db_session.commit()

        workflow = authenticated_client.application.config["kroger_workflow"]
        monkeypatch.setattr(workflow, "ensure_valid_token", lambda user: "valid-token")
        monkeypatch.setattr(workflow, "handle_send_to_cart", lambda token: True)

        captured = {}

        def fake_send_household_email(
            recipient_ids,
            removed_exported_items,
            include_grocery_list,
            grocery_list_items,
            skipped_items,
        ):
            captured["recipient_ids"] = recipient_ids
            captured["removed_exported_items"] = removed_exported_items
            captured["include_grocery_list"] = include_grocery_list
            captured["grocery_list_items"] = grocery_list_items
            captured["skipped_items"] = skipped_items
            return 1

        monkeypatch.setattr(
            "routes.kroger._send_household_kroger_order_created_emails",
            fake_send_household_email,
        )

        with authenticated_client.session_transaction() as sess:
            sess["household_id"] = sample_household.id
            sess["skipped_ingredients"] = ["1 unit eggs", "2 cups spinach"]

        response = authenticated_client.get(
            f"/send-to-cart?confirmed=true&email_recipient_ids={second_user.id}&include_grocery_list=true",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "https://www.kroger.com/cart"
        assert captured == {
            "recipient_ids": [second_user.id],
            "removed_exported_items": False,
            "include_grocery_list": True,
            "grocery_list_items": ["1 unit milk", "1 unit bread"],
            "skipped_items": ["1 unit eggs", "2 cups spinach"],
        }

    def test_send_to_cart_remove_added_keeps_skipped_items(
        self,
        authenticated_client,
        db_session,
        monkeypatch,
        sample_household,
        sample_user,
        sample_grocery_list,
    ):
        """Removing exported items should leave skipped grocery-list items in place."""
        milk_item = self._add_grocery_list_item(db_session, sample_grocery_list, "milk")
        self._add_grocery_list_item(db_session, sample_grocery_list, "bread")

        sample_user.oauth_token = "valid-token"
        sample_user.refresh_token = "refresh-token"
        sample_household.kroger_user_id = sample_user.id
        db_session.commit()

        workflow = authenticated_client.application.config["kroger_workflow"]
        monkeypatch.setattr(workflow, "ensure_valid_token", lambda user: "valid-token")
        monkeypatch.setattr(workflow, "handle_send_to_cart", lambda token: True)

        with authenticated_client.session_transaction() as sess:
            sess["household_id"] = sample_household.id
            sess["selected_recipe_ids"] = ["recipe-1"]
            sess["skipped_ingredients"] = ["1 unit milk"]
            sess["skipped_grocery_list_item_ids"] = [milk_item.id]

        response = authenticated_client.get(
            "/send-to-cart?confirmed=true&remove_added=true", follow_redirects=False
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "https://www.kroger.com/cart"

        remaining_items = GroceryListItem.query.filter_by(
            grocery_list_id=sample_grocery_list.id
        ).all()
        assert [item.recipe_ingredient.ingredient_name for item in remaining_items] == [
            "milk"
        ]

        with authenticated_client.session_transaction() as sess:
            assert "selected_recipe_ids" not in sess
            assert "skipped_ingredients" not in sess
            assert "skipped_grocery_list_item_ids" not in sess

    def test_send_to_cart_remove_added_clears_list_when_nothing_skipped(
        self,
        authenticated_client,
        db_session,
        monkeypatch,
        sample_household,
        sample_user,
        sample_grocery_list,
    ):
        """Removing exported items with no skipped items should clear the grocery list."""
        self._add_grocery_list_item(db_session, sample_grocery_list, "milk")
        self._add_grocery_list_item(db_session, sample_grocery_list, "bread")

        sample_user.oauth_token = "valid-token"
        sample_user.refresh_token = "refresh-token"
        sample_household.kroger_user_id = sample_user.id
        db_session.commit()

        workflow = authenticated_client.application.config["kroger_workflow"]
        monkeypatch.setattr(workflow, "ensure_valid_token", lambda user: "valid-token")
        monkeypatch.setattr(workflow, "handle_send_to_cart", lambda token: True)

        with authenticated_client.session_transaction() as sess:
            sess["household_id"] = sample_household.id
            sess["selected_recipe_ids"] = ["recipe-1"]

        response = authenticated_client.get(
            "/send-to-cart?confirmed=true&remove_added=true", follow_redirects=False
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "https://www.kroger.com/cart"
        assert (
            GroceryListItem.query.filter_by(
                grocery_list_id=sample_grocery_list.id
            ).count()
            == 0
        )

        with authenticated_client.session_transaction() as sess:
            assert "selected_recipe_ids" not in sess

    def test_send_to_cart_continue_keeps_grocery_list_intact(
        self,
        authenticated_client,
        db_session,
        monkeypatch,
        sample_household,
        sample_user,
        sample_grocery_list,
    ):
        """The standard continue path should not change the grocery list."""
        milk_item = self._add_grocery_list_item(db_session, sample_grocery_list, "milk")
        self._add_grocery_list_item(db_session, sample_grocery_list, "bread")

        sample_user.oauth_token = "valid-token"
        sample_user.refresh_token = "refresh-token"
        sample_household.kroger_user_id = sample_user.id
        db_session.commit()

        workflow = authenticated_client.application.config["kroger_workflow"]
        monkeypatch.setattr(workflow, "ensure_valid_token", lambda user: "valid-token")
        monkeypatch.setattr(workflow, "handle_send_to_cart", lambda token: True)

        with authenticated_client.session_transaction() as sess:
            sess["household_id"] = sample_household.id
            sess["skipped_ingredients"] = ["1 unit milk"]
            sess["skipped_grocery_list_item_ids"] = [milk_item.id]

        response = authenticated_client.get(
            "/send-to-cart?confirmed=true", follow_redirects=False
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "https://www.kroger.com/cart"

        remaining_items = GroceryListItem.query.filter_by(
            grocery_list_id=sample_grocery_list.id
        ).all()
        assert [item.recipe_ingredient.ingredient_name for item in remaining_items] == [
            "milk",
            "bread",
        ]


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
