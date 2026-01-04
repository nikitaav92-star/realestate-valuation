"""Direct implementation of FIAS Public API client."""
from __future__ import annotations

import logging
import re
from typing import Optional, Dict, Any, List

import httpx

LOGGER = logging.getLogger(__name__)

FIAS_BASE_URL = "https://fias.nalog.ru"
FIAS_API_URL = f"{FIAS_BASE_URL}/WebServices/Public/DownloadService.asmx"


def get_token_sync() -> str:
    """Get public token from FIAS service.
    
    Returns
    -------
    str
        Public token for FIAS API
        
    Raises
    ------
    ValueError
        If token cannot be obtained
    """
    try:
        # Get token from main page
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(FIAS_BASE_URL)
            response.raise_for_status()
            
            # Extract token from page (look for token in script tags or data attributes)
            content = response.text
            
            # Try to find token in various formats
            # Pattern 1: window.token = "..."
            token_match = re.search(r'window\.token\s*=\s*["\']([^"\']+)["\']', content)
            if token_match:
                return token_match.group(1)
            
            # Pattern 2: data-token="..."
            token_match = re.search(r'data-token=["\']([^"\']+)["\']', content)
            if token_match:
                return token_match.group(1)
            
            # Pattern 3: token: "..."
            token_match = re.search(r'token\s*:\s*["\']([^"\']+)["\']', content)
            if token_match:
                return token_match.group(1)
            
            # Pattern 4: Look for GUID-like token
            token_match = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', content, re.IGNORECASE)
            if token_match:
                return token_match.group(1)
            
            raise ValueError("Token not found in page content")
            
    except httpx.HTTPError as e:
        raise ValueError(f"Failed to get token: HTTP {e.response.status_code if hasattr(e, 'response') else 'unknown'}")
    except Exception as e:
        raise ValueError(f"Failed to get token: {e}")


def search_address(query: str, token: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search for addresses using FIAS Public API.
    
    Parameters
    ----------
    query : str
        Address search query
    token : str, optional
        FIAS token (will be obtained automatically if not provided)
    
    Returns
    -------
    list of dict
        List of found addresses
    """
    if not token:
        try:
            token = get_token_sync()
        except Exception as e:
            LOGGER.warning(f"Failed to get FIAS token: {e}")
            return []
    
    try:
        # Use search endpoint (need to find correct endpoint)
        # Try direct search via API
        search_url = f"{FIAS_BASE_URL}/api/search"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        # Try with token in header
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-Token"] = token
        
        payload = {
            "query": query,
            "limit": 10
        }
        
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            # Try POST first
            try:
                response = client.post(search_url, json=payload, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict) and "results" in data:
                        return data["results"]
            except:
                pass
            
            # Try GET
            try:
                params = {"q": query, "limit": 10}
                if token:
                    params["token"] = token
                response = client.get(search_url, params=params, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict) and "results" in data:
                        return data["results"]
            except:
                pass
            
            # Fallback: try alternative endpoint
            alt_url = f"{FIAS_BASE_URL}/api/v1/search"
            try:
                response = client.post(alt_url, json=payload, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict) and "results" in data:
                        return data["results"]
            except:
                pass
            
            LOGGER.debug(f"FIAS search API returned status {response.status_code}")
            return []
            
    except Exception as e:
        LOGGER.debug(f"FIAS search failed: {e}")
        return []


def normalize_address_fias_direct(address: str) -> Optional[Dict[str, Any]]:
    """Normalize address using direct FIAS API calls.
    
    This is a simplified implementation that tries to use FIAS API directly.
    
    Parameters
    ----------
    address : str
        Raw address string
    
    Returns
    -------
    dict or None
        Normalized address data
    """
    if not address or len(address.strip()) < 5:
        return None
    
    try:
        # Try to get token
        token = get_token_sync()
        
        # Search for address
        results = search_address(address, token)
        
        if not results:
            return None
        
        # Take first result
        result = results[0]
        
        # Extract data
        fias_address = result.get("address") or result.get("full_address") or result.get("name")
        fias_id = result.get("fias_id") or result.get("guid") or result.get("id")
        
        if not fias_address:
            return None
        
        return {
            "fias_address": fias_address,
            "fias_id": fias_id,
            "postal_code": None,
            "quality_code": 0 if fias_id else 1,
        }
        
    except Exception as e:
        LOGGER.debug(f"FIAS direct normalization failed: {e}")
        return None

