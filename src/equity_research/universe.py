from dataclasses import dataclass


@dataclass(frozen=True)
class Equity:
    symbol: str
    name: str
    provider_symbol: str
    exchange: str
    calendar: str
    currency: str
    timezone: str
    lot_size: int


UNIVERSE = {
    "S63": Equity("S63", "ST Engineering", "S63.SI", "SGX", "XSES", "SGD", "Asia/Singapore", 100),
    "D05": Equity("D05", "DBS", "D05.SI", "SGX", "XSES", "SGD", "Asia/Singapore", 100),
    "NVDA": Equity("NVDA", "Nvidia", "NVDA", "NASDAQ", "NASDAQ", "USD", "America/New_York", 1),
    "MSFT": Equity("MSFT", "Microsoft", "MSFT", "NASDAQ", "NASDAQ", "USD", "America/New_York", 1),
}
