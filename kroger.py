"""Kroger API integration and related business logic."""

import requests
import json
import base64
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlencode
from flask import session, redirect, url_for, g


class KrogerAPIService:
    """Service class for Kroger API interactions."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://api.kroger.com/v1"
        self.oauth_base_url = "https://api.kroger.com/v1/connect/oauth2"

    def _encode_client_credentials(self) -> str:
        """Encode client credentials for API authentication."""
        client_credentials = f"{self.client_id}:{self.client_secret}"
        return base64.b64encode(client_credentials.encode()).decode()

    def _get_auth_headers(self, token: str) -> Dict[str, str]:
        """Get authorization headers for API requests."""
        return {
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}'
        }

    def _get_token_headers(self) -> Dict[str, str]:
        """Get headers for token requests."""
        encoded_credentials = self._encode_client_credentials()
        return {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

    def _make_request(self, method: str, url: str, headers: Dict[str, str],
                     data: Optional[str] = None, params: Optional[Dict] = None) -> Optional[requests.Response]:
        """Make HTTP request with error handling."""
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, data=data, timeout=10)
            elif method.upper() == 'PUT':
                response = requests.put(url, headers=headers, data=data, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Kroger API request failed: {e}")
            return None

    def _safe_get_json_value(self, response_json: Dict[str, Any], key: str, default: Any = None) -> Any:
        """Safely extract value from JSON response."""
        return response_json.get(key, default)

    def build_oauth_url(self, base_url: str, redirect_uri: str, scope: str) -> str:
        """Build OAuth authorization URL."""
        params = {
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': scope
        }
        return f"{base_url}/authorize?{urlencode(params)}"

    def get_access_token(self, authorization_code: str, redirect_uri: str) -> Tuple[Optional[str], Optional[str]]:
        """Exchange authorization code for access token."""
        scope = 'cart.basic:write product.compact profile.compact'
        headers = self._get_token_headers()

        body = urlencode({
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'redirect_uri': redirect_uri,
            'scope': scope
        })

        token_url = f"{self.oauth_base_url}/token"
        response = self._make_request('POST', token_url, headers, body)

        if response and response.status_code == 200:
            response_json = response.json()
            access_token = self._safe_get_json_value(response_json, 'access_token')
            refresh_token = self._safe_get_json_value(response_json, 'refresh_token')
            return access_token, refresh_token

        return None, None

    def refresh_access_token(self, refresh_token: str) -> Tuple[Optional[str], Optional[str]]:
        """Refresh the access token."""
        headers = self._get_token_headers()

        body = urlencode({
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        })

        token_url = f"{self.oauth_base_url}/token"
        response = self._make_request('POST', token_url, headers, body)

        if response and response.status_code == 200:
            response_json = response.json()
            new_access_token = self._safe_get_json_value(response_json, 'access_token')
            new_refresh_token = self._safe_get_json_value(response_json, 'refresh_token')
            return new_access_token, new_refresh_token

        return None, None

    def get_profile_id(self, token: str) -> Optional[str]:
        """Fetch the Kroger Profile ID."""
        profile_url = f"{self.base_url}/identity/profile"
        headers = self._get_auth_headers(token)

        response = self._make_request('GET', profile_url, headers)

        if response and response.status_code == 200:
            response_json = response.json()
            return self._safe_get_json_value(response_json, 'data', {}).get('id')

        print("Failed to get profile ID:", response.content if response else "No response")
        return None

    def get_stores(self, zipcode: str, token: str, limit: int = 5) -> Optional[List[Tuple[str, str, str]]]:
        """Fetch Kroger stores based on zipcode."""
        api_url = f"{self.base_url}/locations"
        params = {
            "filter.zipCode.near": zipcode,
            "filter.limit": limit,
            "filter.chain": "Kroger"
        }
        headers = self._get_auth_headers(token)

        response = self._make_request('GET', api_url, headers, params=params)

        if response and response.status_code == 200:
            stores = []
            data = self._safe_get_json_value(response.json(), 'data', [])

            for store in data:
                address_info = self._safe_get_json_value(store, 'address', {})
                address = self._safe_get_json_value(address_info, 'addressLine1', '')
                city = self._safe_get_json_value(address_info, 'city', '')
                location_id = self._safe_get_json_value(store, 'locationId', '')

                if address and city and location_id:
                    stores.append((address, city, location_id))

            return stores

        return None

    def search_products(self, ingredient: str, location_id: str, token: str, limit: int = 10) -> Optional[Dict]:
        """Search for products by ingredient name."""
        api_url = f"{self.base_url}/products"
        params = {
            'filter.term': ingredient,
            'filter.locationId': location_id,
            'filter.limit': limit
        }
        headers = self._get_auth_headers(token)

        response = self._make_request('GET', api_url, headers, params=params)

        if response and response.status_code == 200:
            return response.json()

        print(f"Failed to fetch data for ingredient: {ingredient}")
        return None

    def add_items_to_cart(self, items: List[Dict], token: str) -> bool:
        """Add items to user's Kroger cart."""
        # Prepare items with required fields
        prepared_items = []
        for item in items:
            prepared_item = {
                'quantity': item.get('quantity', 1),
                'upc': item.get('upc'),
                'modality': item.get('modality', 'PICKUP'),
                'allowSubstitutes': item.get('allowSubstitutes', True),
                'specialInstructions': item.get('specialInstructions', '')
            }
            prepared_items.append(prepared_item)

        print(f"=== ADD ITEMS TO CART DEBUG ===")
        print(f"Prepared items: {prepared_items}")

        url = f"{self.base_url}/cart/add"
        headers = self._get_auth_headers(token)
        headers['Content-Type'] = 'application/json'

        data = json.dumps({'items': prepared_items})
        print(f"Request data: {data}")

        response = self._make_request('PUT', url, headers, data)

        if response:
            print(f"Response status: {response.status_code}")
            print(f"Response text: {response.text}")

        if response and 200 <= response.status_code < 300:
            print("Successfully added items to cart")
            return True

        print(f"Failed to add items to cart (status code: {response.status_code if response else 'No response'})")
        return False


class KrogerSessionManager:
    """Manages Kroger-related session data."""

    @staticmethod
    def initialize_kroger_session():
        """Initialize Kroger-specific session values."""
        kroger_defaults = {
            'products_for_cart': [],
            'items_to_choose_from': []
        }

        for key, default_value in kroger_defaults.items():
            if key not in session:
                session[key] = default_value

    @staticmethod
    def clear_kroger_session_data():
        """Clear Kroger-related session data after cart operations."""
        session_keys_to_clear = [
            'products_for_cart',
            'items_to_choose_from',
            'location_id',
            'stores',
            'ingredient_details'
        ]

        for key in session_keys_to_clear:
            session.pop(key, None)

        session['show_modal'] = False

    @staticmethod
    def store_selected_store(store_id: str):
        """Store user selected store ID in session."""
        session['location_id'] = store_id

    @staticmethod
    def store_stores(stores: List[Tuple[str, str, str]]):
        """Store available stores in session."""
        session['stores'] = stores

    @staticmethod
    def get_ingredient_names_from_grocery_list():
        """Get ingredient details from current grocery list and store in session."""
        if not session.get('ingredient_details'):
            ingredient_details = []
            for ingredient in g.grocery_list.recipe_ingredients:
                ingredient_details.append({
                    'name': ingredient.ingredient_name,
                    'quantity': ingredient.quantity,
                    'measurement': ingredient.measurement
                })
            session['ingredient_details'] = ingredient_details
        return session.get('ingredient_details', [])

    @staticmethod
    def get_next_ingredient() -> Optional[Dict]:
        """Get next ingredient to search for."""
        ingredient_details = session.get('ingredient_details', [])
        return ingredient_details.pop(0) if ingredient_details else None

    @staticmethod
    def store_product_choices(products: List[Dict], current_ingredient_detail: Dict = None):
        """Store product choices in session."""
        session['items_to_choose_from'] = products
        session['current_ingredient_detail'] = current_ingredient_detail

    @staticmethod
    def add_product_to_cart(product_id: str) -> bool:
        """Add selected product to cart session."""
        # Initialize session defaults if they don't exist
        if 'products_for_cart' not in session:
            session['products_for_cart'] = []
        if 'items_to_choose_from' not in session:
            session['items_to_choose_from'] = []

        print(f"=== ADD PRODUCT TO CART DEBUG ===")
        print(f"Product ID to add: {product_id}")
        print(f"Current items_to_choose_from: {session.get('items_to_choose_from', [])}")
        print(f"Current products_for_cart: {session.get('products_for_cart', [])}")

        for item in session.get('items_to_choose_from', []):
            print(f"Checking item: {item}")
            if item['id'] == product_id:
                session['products_for_cart'].append(item['id'])
                session['items_to_choose_from'] = []
                print(f"Added {product_id} to cart. New cart: {session['products_for_cart']}")
                return True

        print(f"Product {product_id} not found in items_to_choose_from")
        return False

    @staticmethod
    def has_more_ingredients() -> bool:
        """Check if there are more ingredients to process."""
        return bool(session.get('ingredient_details'))

    @staticmethod
    def get_cart_products() -> List[str]:
        """Get products selected for cart."""
        cart_products = session.get('products_for_cart', [])
        print(f"=== GET CART PRODUCTS DEBUG ===")
        print(f"Cart products: {cart_products}")
        return cart_products


class KrogerWorkflow:
    """Handles Kroger integration workflow logic."""

    def __init__(self, kroger_service: KrogerAPIService):
        self.kroger_service = kroger_service
        self.session_manager = KrogerSessionManager()

    def handle_authentication(self, user, oauth_base_url: str, redirect_url: str) -> str:
        """Handle Kroger authentication workflow."""
        if user.oath_token:
            # Try to refresh the token first
            try:
                new_oath_token, refresh_token = self.kroger_service.refresh_access_token(user.refresh_token)
                if new_oath_token:
                    user.oath_token = new_oath_token
                    user.refresh_token = refresh_token
                    print("TOKEN REFRESHED SUCCESSFULLY - SKIPPING AUTH")
                    return url_for('homepage') + '#modal-zipcode'  # Skip auth, go straight to zipcode
                else:
                    print("TOKEN REFRESH FAILED - CLEARING TOKENS")
                    # Clear invalid tokens
                    user.oath_token = None
                    user.refresh_token = None
                    user.profile_id = None
            except Exception as e:
                print(f"Token refresh error: {e} - CLEARING TOKENS")
                user.oath_token = None
                user.refresh_token = None
                user.profile_id = None

        # Only build auth URL if we don't have valid tokens
        scope = 'cart.basic:write product.compact profile.compact'
        auth_url = self.kroger_service.build_oauth_url(oauth_base_url, redirect_url, scope)
        print("NO VALID TOKEN - REDIRECTING TO AUTH")
        return auth_url

    def handle_callback(self, authorization_code: str, user, redirect_url: str) -> bool:
        """Handle OAuth callback and token management."""
        if user.oath_token:
            try:
                new_oath_token, refresh_token = self.kroger_service.refresh_access_token(user.refresh_token)
                if new_oath_token:
                    user.oath_token = new_oath_token
                    user.refresh_token = refresh_token
                    return True
                else:
                    print("Failed to refresh token. Keeping old token.")
                    return False
            except Exception as e:
                print(f"An error occurred while refreshing the token: {e}")
                return False
        else:
            try:
                access_token, refresh_token = self.kroger_service.get_access_token(authorization_code, redirect_url)
                profile_id = self.kroger_service.get_profile_id(access_token)
                user.oath_token = access_token
                user.refresh_token = refresh_token
                user.profile_id = profile_id
                return True
            except Exception as e:
                print(f"An error occurred while fetching the new token: {e}")
                return False

    def handle_location_search(self, zipcode: str, token: str) -> str:
        """Handle store location search and return redirect URL."""
        stores = self.kroger_service.get_stores(zipcode, token)
        if stores:
            self.session_manager.store_stores(stores)
            return url_for('homepage') + '#modal-store'
        else:
            return url_for('homepage') + '#modal-zipcode'

    def handle_store_selection(self, store_id: str) -> str:
        """Handle store selection and return redirect URL."""
        self.session_manager.store_selected_store(store_id)
        return url_for('kroger_product_search')

    def handle_product_search(self, token: str) -> str:
        """Handle product search workflow and return redirect URL."""
        self.session_manager.get_ingredient_names_from_grocery_list()
        next_ingredient_detail = self.session_manager.get_next_ingredient()

        if next_ingredient_detail:
            response = self.kroger_service.search_products(
                next_ingredient_detail['name'],
                session.get('location_id'),
                token
            )
            if response:
                products = parse_kroger_products(response)
                self.session_manager.store_product_choices(products, next_ingredient_detail)

        return url_for('homepage') + '#modal-ingredient'

    def handle_item_choice(self, product_id: str) -> str:
        """Handle user's product choice and return redirect URL."""
        self.session_manager.add_product_to_cart(product_id)

        if self.session_manager.has_more_ingredients():
            return url_for('kroger_product_search')
        else:
            return url_for('kroger_send_to_cart')

    def handle_send_to_cart(self, token: str) -> str:
        """Handle sending items to Kroger cart and return redirect URL."""
        selected_upcs = self.session_manager.get_cart_products()
        print(f"=== SEND TO CART DEBUG ===")
        print(f"Selected UPCs: {selected_upcs}")
        print(f"Number of items: {len(selected_upcs)}")

        items = [{"quantity": 1, "upc": upc, "modality": "PICKUP"} for upc in selected_upcs]
        print(f"Items to send: {items}")

        success = self.kroger_service.add_items_to_cart(items, token)
        print(f"Add to cart success: {success}")

        self.session_manager.clear_kroger_session_data()

        if success:
            return 'https://www.kroger.com/cart'
        else:
            return url_for('homepage')


def parse_kroger_products(json_response: Dict) -> List[Dict[str, str]]:
    """Parse Kroger product response for customer selection."""
    products_data = json_response.get('data', [])
    items_to_choose_from = []

    for product_data in products_data:
        items_info = product_data.get('items', [{}])
        price_info = items_info[0].get('price', {}) if items_info else {}

        product = {
            'name': product_data.get('description', 'N/A'),
            'id': product_data.get('upc', 'N/A'),
            'price': price_info.get('regular', 'N/A')
        }
        items_to_choose_from.append(product)

    return items_to_choose_from
