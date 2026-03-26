"""Tests for recipe scraper functionality."""

import pytest
from unittest.mock import patch, MagicMock
from recipe_scraper import scrape_recipe_data, _clean_url


class TestURLCleaning:
    """Tests for URL parameter cleaning."""

    def test_clean_url_removes_utm_parameters(self):
        """Test that UTM tracking parameters are removed."""
        url = "https://www.example.com/recipe?id=123&utm_source=pinterest&utm_medium=social&utm_campaign=test"
        cleaned = _clean_url(url)
        
        assert "utm_source" not in cleaned
        assert "utm_medium" not in cleaned
        assert "utm_campaign" not in cleaned
        assert "id=123" in cleaned

    def test_clean_url_removes_facebook_tracking(self):
        """Test that Facebook tracking parameters are removed."""
        url = "https://www.example.com/recipe?id=123&fbclid=abc123"
        cleaned = _clean_url(url)
        
        assert "fbclid" not in cleaned
        assert "id=123" in cleaned

    def test_clean_url_preserves_essential_params(self):
        """Test that non-tracking parameters are preserved."""
        url = "https://www.example.com/recipe?id=256610&servings=4"
        cleaned = _clean_url(url)
        
        assert "id=256610" in cleaned
        assert "servings=4" in cleaned

    def test_clean_url_handles_invalid_url(self):
        """Test that invalid URLs are returned as-is."""
        url = "not a valid url"
        cleaned = _clean_url(url)
        
        assert cleaned == url


class TestRecipeScraperErrorHandling:
    """Tests for recipe scraper error handling."""

    @patch('recipe_scraper.requests.get')
    def test_scrape_handles_402_payment_required(self, mock_get):
        """Test that 402 errors provide helpful message."""
        mock_response = MagicMock()
        mock_response.status_code = 402
        mock_response.raise_for_status.side_effect = Exception("402 Client Error: Payment Required")
        mock_get.return_value = mock_response
        
        # Mock the HTTPError properly
        from requests.exceptions import HTTPError
        http_error = HTTPError("402 Client Error: Payment Required")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        result = scrape_recipe_data("https://www.allrecipes.com/recipe/256610/")
        
        assert result["error"] is not None
        assert "payment" in result["error"].lower() or "blocked" in result["error"].lower()

    @patch('recipe_scraper.requests.get')
    def test_scrape_handles_403_forbidden(self, mock_get):
        """Test that 403 errors provide helpful message."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        
        from requests.exceptions import HTTPError
        http_error = HTTPError("403 Client Error: Forbidden")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        mock_get.return_value = mock_response
        
        result = scrape_recipe_data("https://www.example.com/recipe")
        
        assert result["error"] is not None
        assert "forbidden" in result["error"].lower()

    @patch('recipe_scraper.requests.get')
    def test_scrape_handles_404_not_found(self, mock_get):
        """Test that 404 errors provide helpful message."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        from requests.exceptions import HTTPError
        http_error = HTTPError("404 Client Error: Not Found")
        http_error.response = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        mock_get.return_value = mock_response
        
        result = scrape_recipe_data("https://www.example.com/recipe")
        
        assert result["error"] is not None
        assert "not found" in result["error"].lower()

    @patch('recipe_scraper.requests.get')
    def test_scrape_handles_timeout(self, mock_get):
        """Test that timeout errors provide helpful message."""
        from requests.exceptions import Timeout
        mock_get.side_effect = Timeout("Connection timed out")
        
        result = scrape_recipe_data("https://www.example.com/recipe")
        
        assert result["error"] is not None
        assert "timed out" in result["error"].lower()

    @patch('recipe_scraper.requests.get')
    def test_scrape_cleans_url_before_fetching(self, mock_get):
        """Test that URL is cleaned before making request."""
        mock_response = MagicMock()
        mock_response.content = "<html></html>"
        mock_get.return_value = mock_response
        
        url_with_tracking = "https://www.example.com/recipe?id=123&utm_source=pinterest&utm_medium=social"
        scrape_recipe_data(url_with_tracking)
        
        # Verify the cleaned URL was used
        called_url = mock_get.call_args[0][0]
        assert "utm_source" not in called_url
        assert "utm_medium" not in called_url
        assert "id=123" in called_url

