"""
Meal plan service layer for business logic related to meal planning.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, date
from models import db, MealPlanEntry, Recipe, User
from utils import get_est_date
from logging_config import logger


class MealPlanService:
    """Service class for meal plan-related business logic."""

    @staticmethod
    def get_week_range(week_offset: int = 0) -> Tuple[date, date]:
        """
        Get the start and end dates for a week.

        Args:
            week_offset: Number of weeks from current week (0 = current, 1 = next, -1 = previous)

        Returns:
            Tuple of (week_start_date, week_end_date)
        """
        today = get_est_date()
        week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
        week_end = week_start + timedelta(days=6)
        return week_start, week_end

    @staticmethod
    def get_meal_plan_for_week(
        household_id: int,
        week_offset: int = 0,
    ) -> Dict[date, List[MealPlanEntry]]:
        """
        Get meal plan entries for a specific week, organized by date.

        Args:
            household_id: ID of the household
            week_offset: Number of weeks from current week

        Returns:
            Dictionary mapping dates to lists of MealPlanEntry objects
        """
        week_start, week_end = MealPlanService.get_week_range(week_offset)

        entries = (
            MealPlanEntry.query
            .filter_by(household_id=household_id)
            .filter(MealPlanEntry.date >= week_start)
            .filter(MealPlanEntry.date <= week_end)
            .order_by(MealPlanEntry.date, MealPlanEntry.meal_type)
            .all()
        )

        # Organize by date
        meal_plan = {}
        current_date = week_start
        while current_date <= week_end:
            meal_plan[current_date] = [
                entry for entry in entries if entry.date == current_date
            ]
            current_date += timedelta(days=1)

        return meal_plan

    @staticmethod
    def add_meal_plan_entry(
        household_id: int,
        recipe_id: int,
        meal_date: date,
        meal_type: str,
        cook_user_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Tuple[Optional[MealPlanEntry], Optional[str]]:
        """
        Add a new meal plan entry.

        Args:
            household_id: ID of the household
            recipe_id: ID of the recipe
            meal_date: Date of the meal
            meal_type: Type of meal (breakfast, lunch, dinner, snack)
            cook_user_id: Optional ID of user assigned to cook
            notes: Optional notes

        Returns:
            Tuple of (MealPlanEntry object, error message)
        """
        try:
            # Validate meal type
            valid_meal_types = ["breakfast", "lunch", "dinner", "snack"]
            if meal_type.lower() not in valid_meal_types:
                return None, f"Invalid meal type. Must be one of: {', '.join(valid_meal_types)}"

            entry = MealPlanEntry(
                household_id=household_id,
                recipe_id=recipe_id,
                date=meal_date,
                meal_type=meal_type.lower(),
                cook_user_id=cook_user_id,
                notes=notes.strip() if notes else None,
            )
            db.session.add(entry)
            db.session.commit()
            return entry, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding meal plan entry: {e}", exc_info=True)
            return None, "Failed to add meal to plan. Please try again."

    @staticmethod
    def update_meal_plan_entry(
        entry: MealPlanEntry,
        recipe_id: Optional[int] = None,
        meal_date: Optional[date] = None,
        meal_type: Optional[str] = None,
        cook_user_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Update an existing meal plan entry.

        Args:
            entry: MealPlanEntry object to update
            recipe_id: New recipe ID (optional)
            meal_date: New date (optional)
            meal_type: New meal type (optional)
            cook_user_id: New cook user ID (optional)
            notes: New notes (optional)

        Returns:
            Tuple of (success, error_message)
        """
        try:
            if recipe_id is not None:
                entry.recipe_id = recipe_id
            if meal_date is not None:
                entry.date = meal_date
            if meal_type is not None:
                valid_meal_types = ["breakfast", "lunch", "dinner", "snack"]
                if meal_type.lower() not in valid_meal_types:
                    return False, f"Invalid meal type. Must be one of: {', '.join(valid_meal_types)}"
                entry.meal_type = meal_type.lower()
            if cook_user_id is not None:
                entry.cook_user_id = cook_user_id
            if notes is not None:
                entry.notes = notes.strip() if notes else None

            db.session.commit()
            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating meal plan entry: {e}", exc_info=True)
            return False, "Failed to update meal plan entry. Please try again."

    @staticmethod
    def delete_meal_plan_entry(entry: MealPlanEntry) -> Tuple[bool, Optional[str]]:
        """
        Delete a meal plan entry.

        Args:
            entry: MealPlanEntry object to delete

        Returns:
            Tuple of (success, error_message)
        """
        try:
            db.session.delete(entry)
            db.session.commit()
            return True, None

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting meal plan entry: {e}", exc_info=True)
            return False, "Failed to delete meal plan entry. Please try again."

