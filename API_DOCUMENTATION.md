# Auto-Cart API Documentation

This document describes the HTTP endpoints and API structure of Auto-Cart.

## Authentication

Most endpoints require authentication via session cookies. Users must be logged in to access protected routes.

### Authentication Endpoints

#### POST `/register`
Register a new user account.

**Request Body:**
```json
{
  "username": "string",
  "email": "string",
  "password": "string"
}
```

**Response:** Redirects to household setup on success

---

#### POST `/login`
Authenticate a user and create a session.

**Request Body:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response:** Redirects to homepage on success

---

#### GET `/logout`
End the current user session.

**Response:** Redirects to login page

---

## Recipe Endpoints

### GET `/`
Homepage - displays recipe box and grocery list.

**Authentication:** Required

**Response:** HTML page with recipes and current grocery list

---

### POST `/add-recipe`
Add a new recipe to the current household.

**Authentication:** Required

**Request Body:**
```json
{
  "name": "string",
  "url": "string (optional)",
  "ingredients": "string (one per line)",
  "notes": "string (optional)"
}
```

**Response:** Redirects to homepage with success message

---

### POST `/scrape-recipe`
Extract recipe data from a URL using AI.

**Authentication:** Required

**Request Body:**
```json
{
  "url": "string"
}
```

**Response:**
```json
{
  "success": true,
  "recipe": {
    "name": "string",
    "ingredients": "string",
    "url": "string"
  }
}
```

---

### GET `/recipe/<int:recipe_id>`
View a specific recipe.

**Authentication:** Required

**Response:** HTML page with recipe details

---

### POST `/delete-recipe/<int:recipe_id>`
Delete a recipe.

**Authentication:** Required (must be household owner)

**Response:** Redirects to homepage

---

## Grocery List Endpoints

### POST `/add-to-list`
Add recipe ingredients to the current grocery list.

**Authentication:** Required

**Request Body:**
```json
{
  "recipe_ids": ["int", "int", ...]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Ingredients added to grocery list"
}
```

---

### POST `/update_ingredient`
Update a grocery list item.

**Authentication:** Required

**Request Body:**
```json
{
  "ingredient_id": "int",
  "quantity": "string",
  "measurement": "string",
  "name": "string"
}
```

**Response:**
```json
{
  "success": true,
  "ingredient": {
    "id": "int",
    "quantity": "string",
    "measurement": "string",
    "name": "string"
  }
}
```

---

### POST `/remove-from-list`
Remove an item from the grocery list.

**Authentication:** Required

**Request Body:**
```json
{
  "ingredient_id": "int"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Item removed"
}
```

---

### POST `/toggle-checked`
Toggle the checked status of a grocery list item.

**Authentication:** Required

**Request Body:**
```json
{
  "ingredient_id": "int"
}
```

**Response:**
```json
{
  "success": true,
  "checked": true
}
```

---

## Meal Plan Endpoints

### GET `/meal-plan`
View the weekly meal plan.

**Authentication:** Required

**Response:** HTML page with meal plan calendar

---

### POST `/add-meal-plan-entry`
Add a meal to the meal plan.

**Authentication:** Required

**Request Body:**
```json
{
  "date": "YYYY-MM-DD",
  "meal_type": "breakfast|lunch|dinner",
  "recipe_id": "int (optional)",
  "custom_meal_name": "string (optional)",
  "assigned_cook_ids": ["int", "int", ...]
}
```

**Response:** Redirects to meal plan page

---

## Kroger Integration Endpoints

### GET `/kroger-auth`
Initiate Kroger OAuth flow.

**Authentication:** Required

**Response:** Redirects to Kroger authorization page

---

### GET `/callback`
OAuth callback endpoint for Kroger.

**Authentication:** Required

**Query Parameters:**
- `code`: Authorization code from Kroger

**Response:** Redirects to homepage with success message

---

### POST `/add-to-kroger-cart`
Add grocery list items to Kroger cart.

**Authentication:** Required (Kroger account must be connected)

**Response:**
```json
{
  "success": true,
  "message": "Items added to Kroger cart"
}
```

---

## Household Management Endpoints

### GET `/household-settings`
View and manage household settings.

**Authentication:** Required

**Response:** HTML page with household settings

---

### POST `/create-household`
Create a new household.

**Authentication:** Required

**Request Body:**
```json
{
  "name": "string"
}
```

**Response:** Redirects to household setup

---

### POST `/switch-household`
Switch to a different household.

**Authentication:** Required

**Request Body:**
```json
{
  "household_id": "int"
}
```

**Response:** Redirects to homepage

---

## Response Format

### Success Response
```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": { /* optional data */ }
}
```

### Error Response
```json
{
  "success": false,
  "message": "Error description",
  "errors": { /* optional validation errors */ }
}
```

## HTTP Status Codes

- `200 OK` - Request successful
- `302 Found` - Redirect (common for form submissions)
- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

## Rate Limiting

Currently no rate limiting is implemented. This is planned for future releases.

## CORS

CORS is not currently enabled. The API is designed for same-origin requests only.

---

For more information, see the main [README.md](README.md) and [ARCHITECTURE.md](ARCHITECTURE.md).


