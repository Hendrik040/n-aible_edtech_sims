"""Helper functions for authentication module."""
import os
import logging
import urllib.parse
import json
from fastapi import HTTPException, Response, status
from fastapi.responses import RedirectResponse

from modules.auth.provider import google_oauth_provider

logger = logging.getLogger(__name__)
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')


def add_cors_headers(response: Response):
    """Add CORS headers for cookie support"""
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Origin"] = FRONTEND_URL


def create_oauth_success_redirect(user_login_response, access_token: str) -> RedirectResponse:
    """Create proper HTTP redirect for successful OAuth"""
    if hasattr(user_login_response, 'model_dump_json'):
        user_data_json = user_login_response.model_dump_json()
    elif hasattr(user_login_response, 'json'):
        user_data_json = user_login_response.json()
    else:
        user_data_json = json.dumps(user_login_response)
    
    user_data_encoded = urllib.parse.quote(user_data_json)
    token_encoded = urllib.parse.quote(access_token)
    
    redirect_url = f"{FRONTEND_URL}/auth/google/callback?token={token_encoded}&user={user_data_encoded}"
    return RedirectResponse(url=redirect_url, status_code=302)


def create_account_linking_redirect(account_linking_data: dict) -> RedirectResponse:
    """Create proper HTTP redirect for account linking"""
    data_encoded = urllib.parse.quote(json.dumps(account_linking_data))
    redirect_url = f"{FRONTEND_URL}/auth/google/account-linking?data={data_encoded}"
    return RedirectResponse(url=redirect_url, status_code=302)


def create_role_selection_redirect(role_selection_data: dict) -> RedirectResponse:
    """Create proper HTTP redirect for role selection"""
    data_encoded = urllib.parse.quote(json.dumps(role_selection_data))
    redirect_url = f"{FRONTEND_URL}/auth/google/role-selection?data={data_encoded}"
    return RedirectResponse(url=redirect_url, status_code=302)


def validate_oauth_state(state: str) -> dict:
    """Validate OAuth state and return state data if valid"""
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or missing OAuth state"
        )
    
    state_data = google_oauth_provider.state_store.get_state(state)
    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state"
        )
    
    stored_state = state_data.get("original_state")
    if stored_state and not google_oauth_provider.verify_state(state, stored_state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state - state parameter mismatch"
        )
    
    return state_data

