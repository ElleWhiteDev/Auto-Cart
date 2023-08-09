from flask import Flask,render_template, request, url_for, redirect
from secret import CLIENT_ID, OAUTH2_BASE_URL, API_BASE_URL, REDIRECT_URL
from urllib.parse import urlencode

app = Flask(__name__)


@app.route('/')
def homepage():
    access_code = request.url
    return render_template('home.html', access_code=access_code)

@app.route('/login')
def redirect_to_login():
        # Must define all scopes needed for application
    scope = 'product.personalized cart.basic:rw profile.full'

    # Build authorization URL
    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': [REDIRECT_URL],
        'response_type': 'code',
        'scope': scope
    }
    url = f"{OAUTH2_BASE_URL}/authorize?{urlencode(params)}"

    # Redirect to the OAuth2 /authorize page (if using Flask)
    return redirect(url)
