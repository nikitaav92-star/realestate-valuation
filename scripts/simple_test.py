import sys, os
sys.path.insert(0, '/home/ubuntu/realestate')
from etl.valuation import PropertyFeatures, ValuationRequest, HybridEngine, BuildingType, BuildingHeight

f = PropertyFeatures(lat=55.7558, lon=37.6173, area_total=65.0, rooms=2, floor=5, total_floors=9, building_type=BuildingType.PANEL, building_height=BuildingHeight.MEDIUM)
r = ValuationRequest(features=f, k=10, max_distance_km=5.0)
e = HybridEngine()
res = e.estimate(r)
print(f"Price: {res.estimated_price:,.0f} RUB, Confidence: {res.confidence}%, Method: {res.method_used}")
