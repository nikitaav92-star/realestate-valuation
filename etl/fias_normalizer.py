"""FIAS address normalization using FIAS Public API (free only)."""
from __future__ import annotations

import logging
import os
from typing import Optional, Dict, Any

import httpx

LOGGER = logging.getLogger(__name__)

# Try to import FIAS Public API (free)
try:
    from fias_public_api import get_token_sync, SyncFPA
    FIAS_PUBLIC_AVAILABLE = True
    FIAS_USE_LIBRARY = True
except ImportError:
    FIAS_PUBLIC_AVAILABLE = False
    FIAS_USE_LIBRARY = False
    # Try our direct implementation
    try:
        from etl.fias_public_api import normalize_address_fias_direct
        FIAS_PUBLIC_AVAILABLE = True
        FIAS_USE_LIBRARY = False
        LOGGER.info("Using direct FIAS API implementation")
    except ImportError:
        LOGGER.info("FIAS Public API not available; no fallback configured")


def normalize_address_fias_public(address: str) -> Optional[Dict[str, Any]]:
    """Normalize address using free FIAS Public API.
    
    Parameters
    ----------
    address : str
        Raw address string to normalize
    
    Returns
    -------
    dict or None
        Dictionary with normalized address data, or None if fails
    """
    if not FIAS_PUBLIC_AVAILABLE:
        return None
    
    if not address or len(address.strip()) < 5:
        LOGGER.debug(f"Address too short: {address}")
        return None
    
    try:
        if FIAS_USE_LIBRARY:
            # Use library if available
            from fias_public_api import get_token_sync, SyncFPA
            
            # Get token (automatically obtained from public API)
            token = get_token_sync()
            api = SyncFPA(token)
            
            # Search for address
            results = api.search(address.strip())
            
            if not results or len(results) == 0:
                LOGGER.debug(f"No results found for address: {address}")
                return None
            
            # Take first result (most relevant)
            result = results[0]
            
            # Get details for more information
            object_id = result.get("id")
            if object_id:
                try:
                    details = api.details(object_id)
                    fias_id = details.get("fias_id") or details.get("guid")
                    full_address = details.get("address") or details.get("full_address") or result.get("address")
                except Exception:
                    # If details fail, use search result
                    fias_id = result.get("fias_id") or result.get("guid")
                    full_address = result.get("address")
            else:
                fias_id = result.get("fias_id") or result.get("guid")
                full_address = result.get("address")
            
            if not full_address:
                LOGGER.debug(f"No address found in result: {result}")
                return None
            
            # Quality code: 0 = exact match (if found), 1 = good match
            quality_code = 0 if object_id else 1
            
            return {
                "fias_address": full_address,
                "fias_id": fias_id,
                "postal_code": None,  # FIAS Public API doesn't provide postal code
                "quality_code": quality_code,
            }
        else:
            # Use direct implementation
            from etl.fias_public_api import normalize_address_fias_direct
            return normalize_address_fias_direct(address)
        
    except Exception as e:
        LOGGER.debug(f"FIAS Public API failed for '{address}': {e}")
        return None


def normalize_address(address: str, api_key: Optional[str] = None, secret: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Normalize address using only the free FIAS Public API.
    
    Parameters
    ----------
    address : str
        Raw address string to normalize
    api_key : str, optional
        Deprecated. Kept for backward compatibility.
    secret : str, optional
        Deprecated. Kept for backward compatibility.
    
    Returns
    -------
    dict or None
        Dictionary with normalized address data:
        - fias_address: Normalized address string
        - fias_id: FIAS GUID
        - postal_code: 6-digit postal code (None for FIAS Public API)
        - quality_code: Address quality (0=exact, 1=good, 2-5=problems)
        Returns None if normalization fails
    """
    if not address or len(address.strip()) < 5:
        LOGGER.debug(f"Address too short: {address}")
        return None
    
    result = normalize_address_fias_public(address)
    if result:
        LOGGER.debug(f"✅ Address normalized via FIAS Public API: {address[:50]}")
    else:
        LOGGER.warning(f"❌ Failed to normalize address via FIAS: {address[:50]}")
    return result


def batch_normalize_addresses(addresses: list[str], api_key: Optional[str] = None, secret: Optional[str] = None) -> list[Optional[Dict[str, Any]]]:
    """Normalize multiple addresses sequentially using the FIAS Public API."""
    if not addresses:
        return []
    results: list[Optional[Dict[str, Any]]] = []
    for address in addresses:
        results.append(normalize_address(address))
    return results
