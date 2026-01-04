"""
Auction Lots ETL Module

Collects auction data from multiple sources:
- FSSP (Federal Bailiff Service) - enforcement auctions
- Bankruptcy (Fedresurs, lot-online) - bankruptcy sales
- Bank Pledges - bank collateral sales
- DGI Moscow - city property auctions

IMPORTANT: Data stored in separate DB to avoid price contamination!
"""

from .models import AuctionLot, AuctionSource, AuctionStatus, PropertyType
from .base_parser import BaseAuctionParser

__all__ = [
    'AuctionLot',
    'AuctionSource',
    'AuctionStatus',
    'PropertyType',
    'BaseAuctionParser',
]
