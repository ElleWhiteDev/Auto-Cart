// Kroger authentication
function openKrogerAuth() {
    window.location.href = '/authenticate';
}

// Modal functionality
function openModal(modalId) {
    console.log('Opening modal:', modalId);
    const modal = document.getElementById(modalId);
    console.log('Modal element:', modal);
    if (modal) {
        modal.style.display = 'flex';
        modal.style.alignItems = 'center';
        modal.style.justifyContent = 'center';
        modal.style.padding = '1rem';
        console.log('Modal opened successfully');
    } else {
        console.error('Modal not found:', modalId);
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
}

// Close modal when clicking outside
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-container')) {
        e.target.style.display = 'none';
    }
});

// AI Recipe extraction
document.addEventListener('DOMContentLoaded', function() {
    const extractBtn = document.getElementById('extract-ai-btn');
    if (extractBtn) {
        extractBtn.addEventListener('click', async function() {
            const urlInput = document.getElementById('url');

            if (!urlInput) {
                alert('Could not find URL input field');
                return;
            }

            const url = urlInput.value.trim();
            if (!url) {
                alert('Please enter a recipe URL first');
                return;
            }

            // Show loading state
            const btn = this;
            const spinner = document.getElementById('extract-spinner');
            const originalText = btn.innerHTML;

            btn.disabled = true;
            spinner.classList.remove('d-none');
            btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Extracting...';

            try {
                const formData = new FormData();
                formData.append('url', url);

                const response = await fetch('/extract-recipe-form', {
                    method: 'POST',
                    body: formData
                });

                if (response.ok) {
                    const result = await response.json();

                    if (result.success) {
                        populateFormFields(result.data);
                        showFlashMessage('Recipe extracted successfully! Review and edit as needed.', 'success');
                    } else {
                        showFlashMessage(result.error || 'Failed to extract recipe', 'danger');
                    }
                } else {
                    const errorResult = await response.json();
                    showFlashMessage(errorResult.error || 'Failed to extract recipe', 'danger');
                }
            } catch (error) {
                showFlashMessage('Network error. Please try again.', 'danger');
            } finally {
                btn.disabled = false;
                spinner.classList.add('d-none');
                btn.innerHTML = originalText;
            }
        });
    }

    // Standardize ingredients
    const standardizeBtn = document.getElementById('standardize-btn');
    if (standardizeBtn) {
        standardizeBtn.addEventListener('click', async function() {
            const ingredientsField = document.getElementById('ingredients_text');

            if (!ingredientsField) {
                alert('Could not find ingredients field');
                return;
            }

            const ingredientsText = ingredientsField.value.trim();
            if (!ingredientsText) {
                alert('Please enter some ingredients first');
                return;
            }

            // Show loading state
            const btn = this;
            const spinner = document.getElementById('standardize-spinner');
            const originalText = btn.innerHTML;

            btn.disabled = true;
            spinner.classList.remove('d-none');
            btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Standardizing...';

            try {
                const formData = new FormData();
                formData.append('ingredients_text', ingredientsText);

                const response = await fetch('/standardize-ingredients', {
                    method: 'POST',
                    body: formData
                });

                if (response.ok) {
                    const result = await response.json();

                    if (result.success) {
                        ingredientsField.value = result.data.standardized_ingredients;
                        showFlashMessage('Ingredients standardized successfully!', 'success');
                    } else {
                        showFlashMessage(result.error || 'Failed to standardize ingredients', 'danger');
                    }
                } else {
                    const errorResult = await response.json();
                    showFlashMessage(errorResult.error || 'Failed to standardize ingredients', 'danger');
                }
            } catch (error) {
                showFlashMessage('Network error. Please try again.', 'danger');
            } finally {
                btn.disabled = false;
                spinner.classList.add('d-none');
                btn.innerHTML = originalText;
            }
        });
    }

    // Manual ingredient form
    const manualIngredientForm = document.getElementById('manual-ingredient-form');
    if (manualIngredientForm) {
        manualIngredientForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            const input = document.getElementById('manual-ingredient-input');
            const ingredientText = input.value.trim();

            if (!ingredientText) {
                showFlashMessage('Please enter an ingredient', 'danger');
                return;
            }

            // Show loading state
            const submitBtn = this.querySelector('button[type="submit"]');
            const originalText = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

            try {
                const formData = new FormData();
                formData.append('ingredient_text', ingredientText);

                const response = await fetch('/add_manual_ingredient', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (result.success) {
                    showFlashMessage(result.message, 'success');
                    input.value = ''; // Clear the input
                    // Refresh the page immediately to show the new ingredient
                    window.location.reload();
                } else {
                    showFlashMessage(result.error || 'Failed to add ingredient', 'danger');
                }
            } catch (error) {
                showFlashMessage('Network error. Please try again.', 'danger');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
        });
    }

    // Delete ingredient functionality
    const deleteIngredientBtns = document.querySelectorAll('.delete-ingredient-btn');
    deleteIngredientBtns.forEach(btn => {
        btn.addEventListener('click', async function() {
            const ingredientId = this.getAttribute('data-ingredient-id');
            const listItem = this.closest('li');

            // Disable button during request
            this.disabled = true;
            const originalText = this.innerHTML;
            this.innerHTML = '...';

            try {
                const formData = new FormData();
                formData.append('ingredient_id', ingredientId);

                const response = await fetch('/delete_ingredient', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (result.success) {
                    // Remove the ingredient from the DOM
                    listItem.remove();
                    showFlashMessage(result.message, 'success');
                } else {
                    showFlashMessage(result.error || 'Failed to remove ingredient', 'danger');
                    // Re-enable button on error
                    this.disabled = false;
                    this.innerHTML = originalText;
                }
            } catch (error) {
                showFlashMessage('Network error. Please try again.', 'danger');
                // Re-enable button on error
                this.disabled = false;
                this.innerHTML = originalText;
            }
        });
    });
});

// Helper functions
function populateFormFields(data) {
    const nameField = document.getElementById('name');
    const ingredientsField = document.getElementById('ingredients_text');
    const notesField = document.getElementById('notes');

    if (nameField && data.name) {
        nameField.value = data.name;
    }

    if (ingredientsField && data.ingredients_text) {
        ingredientsField.value = data.ingredients_text;
    }

    if (notesField && data.notes) {
        notesField.value = data.notes;
    }
}

function showFlashMessage(message, category) {
    const flashDiv = document.createElement('div');
    flashDiv.className = `alert alert-${category} alert-dismissible fade show`;
    flashDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    // Try to find the form first, otherwise use the grocery list area
    let targetElement = document.querySelector('#user_form');
    if (!targetElement) {
        targetElement = document.querySelector('.grocery-list-content');
    }
    if (!targetElement) {
        targetElement = document.querySelector('.container');
    }

    if (targetElement) {
        targetElement.insertBefore(flashDiv, targetElement.firstChild);
    } else {
        document.body.insertBefore(flashDiv, document.body.firstChild);
    }

    setTimeout(() => {
        flashDiv.remove();
    }, 5000);
}
