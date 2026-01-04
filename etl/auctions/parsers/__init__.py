"""
Auction parsers for different sources.
"""

from .fssp_parser import FSSPParser
from .fedresurs_parser import FedresursParser
from .bank_parser import BankPledgeParser
from .dgi_parser import DGIMoscowParser

__all__ = [
    'FSSPParser',
    'FedresursParser',
    'BankPledgeParser',
    'DGIMoscowParser',
]
