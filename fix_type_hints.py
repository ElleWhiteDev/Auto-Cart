"""
Quick script to fix type hints for Python 3.9 compatibility.
Converts `str | Response` to `Union[str, Response]` etc.
"""

import re
import os

def fix_file(filepath):
    """Fix type hints in a single file."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # Add Union import if not present and we have | type hints
    if ' | ' in content and 'from typing import' in content:
        # Check if Union is already imported
        if 'Union' not in content:
            # Find the typing import line and add Union
            content = re.sub(
                r'(from typing import [^)]+)',
                r'\1, Union',
                content,
                count=1
            )
    elif ' | ' in content and 'from typing import' not in content:
        # Add new import line after other imports
        lines = content.split('\n')
        import_end = 0
        for i, line in enumerate(lines):
            if line.startswith('from ') or line.startswith('import '):
                import_end = i + 1
        lines.insert(import_end, 'from typing import Union')
        content = '\n'.join(lines)
    
    # Replace | with Union syntax
    # Pattern: type1 | type2 -> Union[type1, type2]
    # Handle cases like: str | Response, dict | Response, tuple[dict, int] | Response
    content = re.sub(
        r'(\w+(?:\[[\w\s,]+\])?)\s*\|\s*(\w+)',
        r'Union[\1, \2]',
        content
    )
    
    if content != original_content:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"✅ Fixed {filepath}")
        return True
    return False

# Fix all route files
routes_dir = 'routes'
files_to_fix = [
    os.path.join(routes_dir, 'main.py'),
    os.path.join(routes_dir, 'auth.py'),
    os.path.join(routes_dir, 'recipes.py'),
    os.path.join(routes_dir, 'grocery.py'),
    os.path.join(routes_dir, 'meal_plan.py'),
    os.path.join(routes_dir, 'kroger.py'),
    os.path.join(routes_dir, 'api.py'),
    os.path.join(routes_dir, 'admin.py'),
]

fixed_count = 0
for filepath in files_to_fix:
    if os.path.exists(filepath):
        if fix_file(filepath):
            fixed_count += 1

print(f"\n🎉 Fixed {fixed_count} files for Python 3.9 compatibility!")

