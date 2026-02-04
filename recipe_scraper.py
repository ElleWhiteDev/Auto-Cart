"""Recipe web scraping functionality."""

import requests
import json
import re
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any
from utils import safe_get_json_value
from logging_config import logger


def scrape_recipe_data(url: str) -> Dict[str, Any]:
    """Scrape recipe data from a given URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Try different extraction methods
        recipe_data = extract_jsonld_recipe(soup)
        if recipe_data:
            return recipe_data

        recipe_data = extract_microdata_recipe(soup)
        if recipe_data:
            return recipe_data

        recipe_data = extract_html_patterns(soup)
        if recipe_data:
            return recipe_data

        return {"name": "", "ingredients": [], "instructions": "", "error": "No recipe data found on this page"}

    except requests.exceptions.Timeout:
        return {"name": "", "ingredients": [], "instructions": "", "error": "Request timed out"}
    except requests.exceptions.RequestException as e:
        return {"name": "", "ingredients": [], "instructions": "", "error": f"Failed to fetch page: {str(e)}"}
    except Exception as e:
        return {"name": "", "ingredients": [], "instructions": "", "error": f"Error parsing page: {str(e)}"}


def extract_jsonld_recipe(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    """Extract recipe data from JSON-LD structured data."""
    try:
        json_scripts = soup.find_all('script', type='application/ld+json')

        for script in json_scripts:
            try:
                data = json.loads(script.string)

                # Handle both single objects and arrays
                if isinstance(data, list):
                    data_items = data
                else:
                    data_items = [data]

                for item in data_items:
                    if isinstance(item, dict):
                        recipe_data = _extract_recipe_from_jsonld_item(item)
                        if recipe_data:
                            return recipe_data

            except (json.JSONDecodeError, TypeError):
                continue

    except Exception as e:
        logger.debug(f"JSON-LD extraction error: {e}")

    return None


def _extract_recipe_from_jsonld_item(item: Dict) -> Optional[Dict[str, Any]]:
    """Extract recipe data from a single JSON-LD item."""
    type_field = item.get('@type', '')

    if 'Recipe' in type_field or type_field == 'Recipe':
        name = item.get('name', '')

        # Extract ingredients
        ingredients = []
        recipe_ingredients = item.get('recipeIngredient', [])
        for ingredient in recipe_ingredients:
            if isinstance(ingredient, str):
                ingredients.append(ingredient.strip())
            elif isinstance(ingredient, dict):
                ingredients.append(ingredient.get('text', '').strip())

        # Extract instructions
        instructions = []
        recipe_instructions = item.get('recipeInstructions', [])
        for instruction in recipe_instructions:
            if isinstance(instruction, str):
                instructions.append(instruction.strip())
            elif isinstance(instruction, dict):
                text = instruction.get('text', '') or instruction.get('name', '')
                if text:
                    instructions.append(text.strip())

        instructions_text = '\n'.join(f"{i+1}. {inst}" for i, inst in enumerate(instructions))

        if name or ingredients:
            return {
                "name": name,
                "ingredients": ingredients,
                "instructions": instructions_text,
                "error": None
            }

    return None


def extract_microdata_recipe(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    """Extract recipe data from microdata."""
    try:
        recipe_elem = soup.find(attrs={"itemtype": re.compile(r".*Recipe")})

        if recipe_elem:
            # Extract name
            name_elem = recipe_elem.find(attrs={"itemprop": "name"})
            name = name_elem.get_text(strip=True) if name_elem else ""

            # Extract ingredients
            ingredients = []
            ingredient_elems = recipe_elem.find_all(attrs={"itemprop": "recipeIngredient"})
            for elem in ingredient_elems:
                text = elem.get_text(strip=True)
                if text:
                    ingredients.append(text)

            # Extract instructions
            instructions = []
            instruction_elems = recipe_elem.find_all(attrs={"itemprop": "recipeInstructions"})
            for elem in instruction_elems:
                text = elem.get_text(strip=True)
                if text:
                    instructions.append(text)

            instructions_text = '\n'.join(f"{i+1}. {inst}" for i, inst in enumerate(instructions))

            if name or ingredients:
                return {
                    "name": name,
                    "ingredients": ingredients,
                    "instructions": instructions_text,
                    "error": None
                }

    except Exception as e:
        logger.debug(f"Microdata extraction error: {e}")

    return None


def extract_html_patterns(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    """Extract recipe data using common HTML patterns."""
    try:
        # Common selectors for recipe elements
        name_selectors = [
            'h1.recipe-title', 'h1.entry-title', '.recipe-header h1',
            'h1[class*="recipe"]', 'h1[class*="title"]', '.recipe-name'
        ]

        ingredient_selectors = [
            '.recipe-ingredients li', '.ingredients li', '[class*="ingredient"] li',
            '.recipe-ingredient', '.ingredient-list li'
        ]

        instruction_selectors = [
            '.recipe-instructions li', '.instructions li', '.recipe-directions li',
            '.directions li', '[class*="instruction"] li', '.recipe-method li'
        ]

        # Extract name
        name = ""
        for selector in name_selectors:
            elem = soup.select_one(selector)
            if elem:
                name = elem.get_text(strip=True)
                break

        # Extract ingredients
        ingredients = []
        for selector in ingredient_selectors:
            elems = soup.select(selector)
            if elems:
                for elem in elems:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 3:  # Filter out very short text
                        ingredients.append(text)
                break

        # Extract instructions
        instruction_steps = []
        for selector in instruction_selectors:
            elems = soup.select(selector)
            if elems:
                for elem in elems:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 10:  # Filter out very short text
                        instruction_steps.append(text)
                break

        instructions = ""
        if instruction_steps:
            instructions = '\n'.join(f"{i+1}. {step}" for i, step in enumerate(instruction_steps))

        # Return data if we found something useful
        if name or ingredients or instruction_steps:
            return {
                "name": name or "Untitled Recipe",
                "ingredients": ingredients,
                "instructions": instructions,
                "error": None
            }

    except Exception as e:
        logger.debug(f"HTML pattern extraction error: {e}")

    return None
