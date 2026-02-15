/**
 * Auto-Cart Frontend Application
 * Modern, organized JavaScript for grocery list management
 */

// ============================================================================
// MODAL MANAGEMENT
// ============================================================================

const ModalManager = {
    /**
     * Open a modal by ID
     * @param {string} modalId - The ID of the modal to open
     */
    open(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'flex';
            modal.style.alignItems = 'center';
            modal.style.justifyContent = 'center';
            modal.style.padding = '1rem';
            modal.setAttribute('aria-hidden', 'false');
        } else {
            console.error(`Modal not found: ${modalId}`);
        }
    },

    /**
     * Close a modal by ID
     * @param {string} modalId - The ID of the modal to close
     */
    close(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'none';
            modal.setAttribute('aria-hidden', 'true');
        }
    },

    /**
     * Initialize modal event listeners
     */
    init() {
        // Close modal when clicking outside
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-container')) {
                e.target.style.display = 'none';
                e.target.setAttribute('aria-hidden', 'true');
            }
        });

        // Close modal on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const openModals = document.querySelectorAll('.modal-container[aria-hidden="false"]');
                openModals.forEach(modal => {
                    modal.style.display = 'none';
                    modal.setAttribute('aria-hidden', 'true');
                });
            }
        });
    }
};

// Legacy function support
function openModal(modalId) {
    ModalManager.open(modalId);
}

function closeModal(modalId) {
    ModalManager.close(modalId);
}

// ============================================================================
// KROGER INTEGRATION
// ============================================================================

const KrogerAuth = {
    /**
     * Open Kroger authentication in a new tab
     */
    openAuth() {
        window.open('/authenticate', '_blank');
        window.location.hash = 'modal-closed';
    }
};

// Legacy function support
function openKrogerAuth() {
    KrogerAuth.openAuth();
}

// ============================================================================
// UI UTILITIES
// ============================================================================

const UIUtils = {
    /**
     * Show a flash message to the user
     * @param {string} message - Message to display
     * @param {string} category - Message category (success, danger, warning, info)
     */
    showFlashMessage(message, category = 'info') {
        const flashDiv = document.createElement('div');
        flashDiv.className = `alert alert-${category} alert-dismissible fade show`;
        flashDiv.setAttribute('role', 'alert');
        flashDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;

        // Find appropriate container
        const targetElement =
            document.querySelector('#user_form') ||
            document.querySelector('.grocery-list-content') ||
            document.querySelector('.container') ||
            document.body;

        targetElement.insertBefore(flashDiv, targetElement.firstChild);

        // Auto-dismiss after 5 seconds
        setTimeout(() => flashDiv.remove(), 5000);
    },

    /**
     * Set button loading state
     * @param {HTMLElement} button - Button element
     * @param {boolean} isLoading - Whether button should show loading state
     * @param {string} loadingText - Text to show when loading
     */
    setButtonLoading(button, isLoading, loadingText = 'Loading...') {
        if (isLoading) {
            button.dataset.originalText = button.innerHTML;
            button.disabled = true;
            button.innerHTML = `<span class="spinner-border spinner-border-sm" role="status"></span> ${loadingText}`;
        } else {
            button.disabled = false;
            button.innerHTML = button.dataset.originalText || button.innerHTML;
        }
    },

    /**
     * Populate form fields with data
     * @param {Object} data - Data object with field values
     */
    populateFormFields(data) {
        Object.entries(data).forEach(([fieldName, value]) => {
            const field = document.getElementById(fieldName);
            if (field && value) {
                field.value = value;
            }
        });
    }
};

// Legacy function support
function showFlashMessage(message, category) {
    UIUtils.showFlashMessage(message, category);
}

function populateFormFields(data) {
    UIUtils.populateFormFields(data);
}

// ============================================================================
// RECIPE MANAGEMENT
// ============================================================================

const RecipeManager = {
    /**
     * Extract recipe data from URL using AI
     */
    async extractRecipe() {
        const urlInput = document.getElementById('url');

        if (!urlInput) {
            UIUtils.showFlashMessage('Could not find URL input field', 'danger');
            return;
        }

        const url = urlInput.value.trim();
        if (!url) {
            UIUtils.showFlashMessage('Please enter a recipe URL first', 'warning');
            return;
        }

        const btn = document.getElementById('extract-ai-btn');
        const spinner = document.getElementById('extract-spinner');

        UIUtils.setButtonLoading(btn, true, 'Extracting...');
        if (spinner) spinner.classList.remove('d-none');

        try {
            const formData = new FormData();
            formData.append('url', url);

            const response = await fetch('/extract-recipe-form', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (response.ok && result.success) {
                UIUtils.populateFormFields(result.data);
                UIUtils.showFlashMessage('Recipe extracted successfully! Review and edit as needed.', 'success');
            } else {
                UIUtils.showFlashMessage(result.error || 'Failed to extract recipe', 'danger');
            }
        } catch (error) {
            console.error('Recipe extraction error:', error);
            UIUtils.showFlashMessage('Network error. Please try again.', 'danger');
        } finally {
            UIUtils.setButtonLoading(btn, false);
            if (spinner) spinner.classList.add('d-none');
        }
    },

    /**
     * Standardize ingredients using AI
     */
    async standardizeIngredients() {
        const ingredientsField = document.getElementById('ingredients_text');

        if (!ingredientsField) {
            UIUtils.showFlashMessage('Could not find ingredients field', 'danger');
            return;
        }

        const ingredientsText = ingredientsField.value.trim();
        if (!ingredientsText) {
            UIUtils.showFlashMessage('Please enter some ingredients first', 'warning');
            return;
        }

        const btn = document.getElementById('standardize-btn');
        const spinner = document.getElementById('standardize-spinner');

        UIUtils.setButtonLoading(btn, true, 'Standardizing...');
        if (spinner) spinner.classList.remove('d-none');

        try {
            const formData = new FormData();
            formData.append('ingredients_text', ingredientsText);

            const response = await fetch('/standardize-ingredients', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (response.ok && result.success) {
                ingredientsField.value = result.data.standardized_ingredients;
                UIUtils.showFlashMessage('Ingredients standardized successfully!', 'success');
            } else {
                UIUtils.showFlashMessage(result.error || 'Failed to standardize ingredients', 'danger');
            }
        } catch (error) {
            console.error('Ingredient standardization error:', error);
            UIUtils.showFlashMessage('Network error. Please try again.', 'danger');
        } finally {
            UIUtils.setButtonLoading(btn, false);
            if (spinner) spinner.classList.add('d-none');
        }
    },

    /**
     * Add a manual ingredient to the grocery list
     */
    async addManualIngredient(ingredientText) {
        if (!ingredientText || !ingredientText.trim()) {
            UIUtils.showFlashMessage('Please enter an ingredient', 'warning');
            return false;
        }

        try {
            const formData = new FormData();
            formData.append('ingredient_text', ingredientText.trim());

            const response = await fetch('/add_manual_ingredient', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                UIUtils.showFlashMessage(result.message, 'success');
                // Reload the page to show updated grocery list
                // Use a slight delay to ensure the flash message is visible
                setTimeout(() => {
                    window.location.reload();
                }, 100);
                return true;
            } else {
                UIUtils.showFlashMessage(result.error || 'Failed to add ingredient', 'danger');
                return false;
            }
        } catch (error) {
            console.error('Add ingredient error:', error);
            UIUtils.showFlashMessage('Network error. Please try again.', 'danger');
            return false;
        }
    },

    /**
     * Delete an ingredient from the grocery list
     */
    async deleteIngredient(ingredientId, listItem) {
        try {
            const formData = new FormData();
            formData.append('ingredient_id', ingredientId);

            const response = await fetch('/delete_ingredient', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                listItem.remove();
                UIUtils.showFlashMessage(result.message, 'success');
                return true;
            } else {
                UIUtils.showFlashMessage(result.error || 'Failed to remove ingredient', 'danger');
                return false;
            }
        } catch (error) {
            console.error('Delete ingredient error:', error);
            UIUtils.showFlashMessage('Network error. Please try again.', 'danger');
            return false;
        }
    }
};

// ============================================================================
// APPLICATION INITIALIZATION
// ============================================================================

/**
 * Initialize the application when DOM is ready
 */
document.addEventListener('DOMContentLoaded', () => {
    // Initialize modal manager
    ModalManager.init();

    // Recipe extraction button
    const extractBtn = document.getElementById('extract-ai-btn');
    if (extractBtn) {
        extractBtn.addEventListener('click', () => RecipeManager.extractRecipe());
    }

    // Ingredient standardization button
    const standardizeBtn = document.getElementById('standardize-btn');
    if (standardizeBtn) {
        standardizeBtn.addEventListener('click', () => RecipeManager.standardizeIngredients());
    }

    // Manual ingredient form - handled by inline onsubmit handler in template
    // This ensures the handler is attached before any user interaction

    // Delete ingredient functionality
    const deleteIngredientBtns = document.querySelectorAll('.delete-ingredient-btn');
    deleteIngredientBtns.forEach(btn => {
        btn.addEventListener('click', async function() {
            const ingredientId = this.getAttribute('data-ingredient-id');
            const listItem = this.closest('li');

            UIUtils.setButtonLoading(this, true, '...');

            const success = await RecipeManager.deleteIngredient(ingredientId, listItem);

            if (!success) {
                UIUtils.setButtonLoading(this, false);
            }
        });
    });
});
