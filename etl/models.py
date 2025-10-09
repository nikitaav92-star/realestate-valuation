from pydantic import BaseModel

class Listing(BaseModel):
    id: int
    url: str = ""
    region: int = 0
    deal_type: str = ""
    rooms: int = 0
    area_total: float = 0.0
    floor: int = 0
    address: str = ""
    seller_type: str = ""

class PricePoint(BaseModel):
    id: int
    price: float
