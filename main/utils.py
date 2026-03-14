import secrets
import string
import base64
import hashlib
from urllib.parse import urlencode
import requests

CLIENT_ID = "deepply.com"


def generate_oauth_url(provider_url, state, redirect_url):
    char_set = string.ascii_letters + string.digits
    code_verifier = ''.join(secrets.choice(char_set) for _ in range(128))
    bytes_verifier = code_verifier.encode()
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(bytes_verifier).digest()).rstrip(b'=').decode()

    params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'redirect_uri': redirect_url,
        'code_challenge_method': 'S256',
        'code_challenge': code_challenge,
        'scope': 'email:read',
        'state': state
    }
    redirect = provider_url + urlencode(params)

    return code_verifier, redirect

def get_access_token(code, code_verifier, redirect_url):
    body = {
        'client_id': CLIENT_ID,
        'grant_type': 'authorization_code',
        'code': code,
        'code_verifier': code_verifier,
        'redirect_uri': redirect_url
    }

    response = requests.post("https://lichess.org/api/token", data=body)
    if response.status_code == 200:
        return response.json()
    else:
        print("Error fetching access token:", response.text)
        return None
    
def get_email(access_token):
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.get("https://lichess.org/api/account/email", headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print("Error fetching email:", response.text)
        return None