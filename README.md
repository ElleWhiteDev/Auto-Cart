# Auto-Cart 🛒

## Live Site 🌐: [www.ellewhite.dev](http://www.ellewhite.dev)

## Description 📝

Auto-Cart is designed to simplify your online recipe experience. Input your recipe's URL, ingredients, and any additional notes to save them in your personal recipe box. When you're ready to shop, choose your recipes and Auto-Cart builds your grocery list. You can either use your list to fil a Kroger shopping cart or have it conveniently emailed to you.


## Features 🌟

1. **User Registration and Login**: Secure and personalized user authentication.
2. **Update Email/Password**: Maintain your account details effortlessly.
3. **Delete Account**: Control your data with easy account deletion.
4. **Recipe Box**: A centralized hub for all your treasured recipes.
5. **Export to Kroger**: Directly populate your Kroger shopping cart from your recipe selections.
6. **Email Grocery List**: Alternatively, receive your curated grocery list via email.


## Standard User Flow 🚶

1. **User Sign-up / Login**: Register for an account or log into your existing one.
2. **Add New Recipe**: Input the URL, ingredients, and notes of your chosen recipe.
3. **View Recipe Box**: Review your saved recipes.
4. **Export to Kroger Cart**: Review Kroger's options for the items in grocery list and select choices
5. **Redirect to Kroger**: Upon confirmation, you are redirected to Kroger's website, cart ready for checkout.
6. **Email Grocery List**: As an option, have your grocery list emailed to you for added convenience.

## Technology Stack 🛠️

- **Frontend**: HTML, CSS (Bootstrap)
- **Backend**: Python, Flask
- **Form Handling**: Flask-WTF, WTForms
- **Database**: PostgreSQL
- **Hosting**: AWS (EC2/EIP/RDS) with Apache

## APIs Used 🌐

- Kroger Auth API
- Kroger Product API
- Kroger Cart API

## Additional Features 🎉

- Pure HTML/CSS modals
- Email functionality
