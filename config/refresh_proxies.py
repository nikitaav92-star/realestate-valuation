#!/usr/bin/env python3
"""Script to refresh NodeMaven proxy pool with new session IDs."""
import random
import string
from pathlib import Path
from datetime import datetime

# NodeMaven configuration
NODEMAVEN_USER = "nikita_a_v_92_gmail_com"
NODEMAVEN_PASSWORD = "coss4q1h2r"
NODEMAVEN_HOST = "gate.nodemaven.com:8080"

# Proxy settings
PROXY_COUNT = 10
COUNTRY = "ru"  # Russia
TTL = "24h"  # Time to live
FILTER = "medium"  # Can be: residential, datacenter, medium, premium


def generate_session_id(length=12):
    """Generate random session ID for proxy rotation."""
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def generate_proxy_url(session_id):
    """Generate NodeMaven proxy URL with session ID."""
    username = f"{NODEMAVEN_USER}-country-{COUNTRY}-sid-{session_id}-ttl-{TTL}-filter-{FILTER}"
    return f"http://{username}:{NODEMAVEN_PASSWORD}@{NODEMAVEN_HOST}"


def refresh_proxy_pool(count=PROXY_COUNT):
    """Generate fresh proxy pool with new session IDs."""
    proxies = []
    for i in range(count):
        session_id = generate_session_id()
        proxy_url = generate_proxy_url(session_id)
        proxies.append(proxy_url)
    return proxies


def save_proxy_pool(proxies, output_path="config/proxy_pool.txt"):
    """Save proxy pool to file."""
    output_file = Path(output_path)
    
    # Create backup of old file
    if output_file.exists():
        backup_path = output_file.with_suffix(f".txt.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        output_file.rename(backup_path)
        print(f"📦 Backup created: {backup_path}")
    
    # Write new proxies
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# NodeMaven Proxy Pool ({len(proxies)} proxies)\n")
        f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Format: http://username:password@host:port\n")
        f.write(f"# Country: {COUNTRY.upper()} | TTL: {TTL} | Filter: {FILTER}\n\n")
        
        for proxy in proxies:
            f.write(f"{proxy}\n")
    
    print(f"✅ Saved {len(proxies)} proxies to {output_file}")
    return output_file


def main():
    print("🔄 Refreshing NodeMaven proxy pool...")
    print(f"   Country: {COUNTRY.upper()}")
    print(f"   TTL: {TTL}")
    print(f"   Filter: {FILTER}")
    print(f"   Count: {PROXY_COUNT}\n")
    
    # Generate fresh proxies
    proxies = refresh_proxy_pool(PROXY_COUNT)
    
    # Save to file
    output_path = save_proxy_pool(proxies)
    
    print(f"\n📋 Proxy pool refreshed successfully!")
    print(f"   File: {output_path}")
    print(f"   Proxies: {len(proxies)}")
    
    # Show sample
    print(f"\n📌 Sample proxy (first):" )
    print(f"   {proxies[0]}")


if __name__ == "__main__":
    main()
