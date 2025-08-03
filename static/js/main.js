// Kroger authentication
function openKrogerAuth() {
    window.location.href = '/authenticate';
}

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

    // Delete ingredient functionality
    const deleteIngredientBtns = document.querySelectorAll('.delete-ingredient-btn');
    deleteIngredientBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const ingredientId = this.getAttribute('data-ingredient-id');

            // Remove the confirm dialog
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/delete_ingredient';

            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'ingredient_id';
            input.value = ingredientId;

            form.appendChild(input);
            document.body.appendChild(form);
            form.submit();
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

    const form = document.querySelector('#user_form');
    form.insertBefore(flashDiv, form.firstChild);

    setTimeout(() => {
        flashDiv.remove();
    }, 5000);
}
