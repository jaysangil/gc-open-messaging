# auth.py
import os
import time
import logging
import requests
from typing import Optional

# Token cache
_token_cache: Optional[dict] = None

def get_token(force_refresh: bool = False) -> str:
    """
    Fetches a client-credentials access token from Genesys Cloud with caching.
    
    Args:
        force_refresh: If True, ignores cache and fetches a new token
        
    Returns:
        Valid access token string
        
    Raises:
        ValueError: If required environment variables are missing
        ConnectionError: If the request fails
        TimeoutError: If the request times out
    """
    global _token_cache
    
    # Check cache first (if not forcing refresh)
    if not force_refresh and _token_cache:
        # Check if token is still valid (with 5 minute buffer)
        if time.time() < (_token_cache['expires_at'] - 300):
            logging.debug("Using cached token")
            return _token_cache['token']
    
    # Validate environment variables
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET") 
    api_host = os.getenv("API_HOST")
    
    if not all([client_id, client_secret, api_host]):
        missing = [var for var, val in [
            ("CLIENT_ID", client_id),
            ("CLIENT_SECRET", client_secret),
            ("API_HOST", api_host)
        ] if not val]
        raise ValueError(f"Missing required environment variables: {missing}")
    
    logging.info("Fetching new access token from Genesys Cloud")
    
    try:
        resp = requests.post(
            f"https://login.{api_host}/oauth/token",
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            timeout=10,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        resp.raise_for_status()
        
        token_data = resp.json()
        
        # Validate response structure
        if "access_token" not in token_data:
            raise ValueError("Response missing access_token field")
        
        if "expires_in" not in token_data:
            # Default to 1 hour if not specified
            expires_in = 3600
            logging.warning("Response missing expires_in, defaulting to 1 hour")
        else:
            expires_in = int(token_data["expires_in"])
        
        # Cache the token
        _token_cache = {
            'token': token_data["access_token"],
            'expires_at': time.time() + expires_in
        }
        
        logging.info("Successfully obtained new access token (expires in %d seconds)", expires_in)
        return token_data["access_token"]
        
    except requests.exceptions.Timeout:
        logging.error("Token request timed out")
        raise TimeoutError("Authentication request timed out after 10 seconds")
    except requests.exceptions.HTTPError as e:
        logging.error("HTTP error during token request: %s", e)
        if e.response.status_code == 401:
            raise ConnectionError("Invalid client credentials")
        elif e.response.status_code == 403:
            raise ConnectionError("Client not authorized for this grant type")
        else:
            raise ConnectionError(f"HTTP {e.response.status_code}: {e}")
    except requests.exceptions.RequestException as e:
        logging.error("Request error during token fetch: %s", e)
        raise ConnectionError(f"Authentication request failed: {e}")
    except (KeyError, ValueError, TypeError) as e:
        logging.error("Invalid token response: %s", e)
        raise ValueError(f"Invalid authentication response: {e}")

def clear_token_cache():
    """Clears the cached token (useful for testing or forced refresh)"""
    global _token_cache
    _token_cache = None
    logging.info("Token cache cleared")