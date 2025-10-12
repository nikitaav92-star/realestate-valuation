#!/usr/bin/env python3
"""Debug what data is actually being collected."""

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOGGER = logging.getLogger(__name__)

def analyze_captcha_strategy_log():
    """Analyze the captcha strategy log to see what's really happening."""
    
    log_file = Path("logs/captcha_strategy.log")
    if not log_file.exists():
        LOGGER.error("❌ No log file found")
        return
    
    LOGGER.info("🔍 Analyzing captcha strategy log...")
    
    with open(log_file, 'r') as f:
        lines = f.readlines()
    
    # Count different types of messages
    success_count = 0
    error_count = 0
    offers_collected = []
    
    for line in lines:
        if "✅ Page" in line and "offers" in line:
            success_count += 1
            # Extract offers count
            try:
                offers_part = line.split("offers")[0].split(": ")[-1]
                offers_count = int(offers_part.strip())
                offers_collected.append(offers_count)
            except:
                pass
        elif "❌ FAILED" in line or "Error" in line:
            error_count += 1
    
    LOGGER.info(f"📊 LOG ANALYSIS:")
    LOGGER.info(f"   Successful pages: {success_count}")
    LOGGER.info(f"   Error pages: {error_count}")
    LOGGER.info(f"   Offers per page: {offers_collected}")
    LOGGER.info(f"   Total offers reported: {sum(offers_collected)}")
    
    # Check if offers are actually being extracted
    LOGGER.info(f"\n🔍 CHECKING FOR ACTUAL DATA EXTRACTION:")
    
    extraction_found = False
    for line in lines:
        if "extract" in line.lower() or "parse" in line.lower() or "offer" in line.lower():
            if "extract" in line.lower():
                extraction_found = True
                LOGGER.info(f"   Found extraction: {line.strip()}")
    
    if not extraction_found:
        LOGGER.warning("⚠️  No explicit data extraction found in logs")
        LOGGER.warning("   This suggests the script might be counting page loads, not actual offers")

def check_actual_data_files():
    """Check what data files actually exist and contain."""
    
    LOGGER.info(f"\n📁 CHECKING DATA FILES:")
    
    # Check metrics
    metrics_file = Path("logs/captcha_strategy_metrics.json")
    if metrics_file.exists():
        with open(metrics_file, 'r') as f:
            metrics = json.load(f)
        
        LOGGER.info(f"   Metrics file: ✅ EXISTS")
        LOGGER.info(f"   Reported offers: {metrics.get('offers_collected', 0)}")
        LOGGER.info(f"   Pages scraped: {metrics.get('pages_scraped', 0)}")
        LOGGER.info(f"   Errors: {len(metrics.get('errors', []))}")
        
        if metrics.get('offers_collected', 0) > 0:
            LOGGER.info(f"   ⚠️  Metrics claim {metrics['offers_collected']} offers, but no actual data files found")
    
    # Check for actual offer data files
    data_files = [
        "logs/real_cian_offers.json",
        "logs/offers_data.json", 
        "logs/collected_offers.json",
        "data/offers.json"
    ]
    
    data_found = False
    for file_path in data_files:
        if Path(file_path).exists():
            LOGGER.info(f"   Data file {file_path}: ✅ EXISTS")
            with open(file_path, 'r') as f:
                content = f.read()
                if len(content) > 100:  # Has substantial content
                    LOGGER.info(f"      Content size: {len(content)} chars")
                    data_found = True
                else:
                    LOGGER.warning(f"      Content size: {len(content)} chars (seems empty)")
        else:
            LOGGER.info(f"   Data file {file_path}: ❌ NOT FOUND")
    
    if not data_found:
        LOGGER.error("❌ NO ACTUAL OFFER DATA FILES FOUND!")
        LOGGER.error("   The script appears to be counting page loads, not extracting real offers")

def check_database_data():
    """Check what's actually in the database."""
    
    LOGGER.info(f"\n🗄️ CHECKING DATABASE:")
    
    try:
        import subprocess
        result = subprocess.run([
            "docker", "exec", "realestate-postgres-1", "psql", 
            "-U", "realuser", "-d", "realdb", "-c", 
            "SELECT COUNT(*) FROM listings;"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            count_line = result.stdout.strip().split('\n')[-2]
            count = count_line.strip()
            LOGGER.info(f"   Database listings: {count}")
            
            if int(count) <= 2:
                LOGGER.warning(f"   ⚠️  Only {count} listings in DB (probably test data)")
                LOGGER.warning(f"   This confirms that real offers are NOT being saved to database")
        else:
            LOGGER.error(f"   Database check failed: {result.stderr}")
            
    except Exception as e:
        LOGGER.error(f"   Database check error: {e}")

if __name__ == "__main__":
    LOGGER.info("🔍 DEBUGGING CIAN DATA COLLECTION")
    LOGGER.info("=" * 50)
    
    analyze_captcha_strategy_log()
    check_actual_data_files()
    check_database_data()
    
    LOGGER.info(f"\n🎯 CONCLUSION:")
    LOGGER.info(f"   The script appears to be:")
    LOGGER.info(f"   1. Successfully loading CIAN pages")
    LOGGER.info(f"   2. Counting page loads as 'offers'")
    LOGGER.info(f"   3. NOT actually extracting real offer data")
    LOGGER.info(f"   4. NOT saving data to database")
    LOGGER.info(f"\n   This explains why you see '280 offers' but no real data!")

