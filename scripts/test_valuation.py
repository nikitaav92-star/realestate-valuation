#!/usr/bin/env python3
"""Test valuation system end-to-end."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etl.valuation import (
    PropertyFeatures, ValuationRequest, HybridEngine,
    BuildingType, BuildingHeight
)

print("=" * 80)
print("🧪 VALUATION SYSTEM TEST")
print("=" * 80)

# Create test property
features = PropertyFeatures(
    lat=55.7558,
    lon=37.6173,
    area_total=65.0,
    rooms=2,
    floor=5,
    total_floors=9,
    building_type=BuildingType.PANEL,
    building_height=BuildingHeight.MEDIUM
)

request = ValuationRequest(
    features=features,
    k=10,
    max_distance_km=5.0,
    max_age_days=90
)

print("\n📋 Test Property:")
print(f"  Location: {features.lat}, {features.lon}")
print(f"  Area: {features.area_total} m²")
print(f"  Rooms: {features.rooms}")
print(f"  Floor: {features.floor}/{features.total_floors}")
print(f"  Type: {features.building_type.value}")
print()

# Run valuation
print("🔄 Running valuation...\n")

try:
    engine = HybridEngine()
    result = engine.estimate(request)
    
    print("=" * 80)
    print("✅ VALUATION RESULT")
    print("=" * 80)
    print()
    print(result.summary())
    print()
    
    if result.knn_estimate:
        print(f"\n🔍 KNN Details:")
        print(f"  Comparables found: {len(result.knn_estimate.comparables)}")
        print(f"  KNN confidence: {result.knn_estimate.confidence}%")
        print(f"\n  Top 5 comparables:")
        for i, comp in enumerate(result.knn_estimate.comparables[:5], 1):
            print(f"    {i}. ID {comp.listing_id}: {comp.price:,.0f} ₽ "
                  f"({comp.distance_km:.1f}km, sim={comp.similarity_score:.0f}%, "
                  f"weight={comp.weight:.2f})")
    
    if result.grid_estimate:
        print(f"\n📊 Grid Details:")
        print(f"  Fallback level: {result.grid_estimate.fallback_level}")
        print(f"  Sample size: {result.grid_estimate.sample_size}")
        print(f"  Grid confidence: {result.grid_estimate.confidence}%")
    
    print("\n" + "=" * 80)
    print("✅ TEST PASSED")
    print("=" * 80)

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
