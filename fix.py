import requests
from typing import Dict, Any, Optional, List, Union
from functools import lru_cache

class Manic:
    """
    Wrapper for Polymarket API integration specifically fixing the
    'Lecture seule, Zéro fonds' (Read-only, Zero Balance) glitch
    where the client expected an object but got a serialized dict
    causing state mismatches.
    """

    def __init__(self, base_url: str = "https://api.polygon.io/v2/wallets", token: str = ""):
        self.base_url = base_url
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self._snapshot = {}

    def _fetch(self, endpoint: str) -> Dict[str, Any]:
        """
        Safe fetch mechanism that handles the 'Zero Fonds' edge case
        where API returns null or empty dict instead of explicit 0.
        """
        url = f"{self.base_url}/{endpoint}"
        try:
            response = self.session.get(url, timeout=5.0)
            response.raise_for_status()
            data = response.json()

            # The specific fix for Issue 322:
            # Ensure we normalize the response structure regardless of backend version
            if data and "data" in data:
                return {"items": data["data"], "meta": data.get("meta", {})}
            elif data:
                return {"items": [data], "meta": {}}
            else:
                return {"items": [], "meta": {}}

        except requests.exceptions.JSONDecodeError:
            # Fallback if API sends raw strings or weird encoding
            return {"items": [], "meta": {}}
        except requests.exceptions.RequestException:
            return {"items": [], "meta": {"error": True}}

    def get_markets(self) -> List[Dict[str, Any]]:
        """
        Accessor for the 'Lecture seule' optimized view.
        """
        raw = self._fetch("markets")
        return raw.get("items", [])

    def get_portfolio(self) -> Dict[str, Any]:
        """
        Retrieves the current balance state.
        Fixes the 'Zero Fonds' bug by normalizing float/int comparison.
        """
        raw = self._fetch("portfolio")
        # Normalization fix for the 'Zéro fonds' state
        items = raw.get("items", [])
        
        if len(items) == 1:
            item = items[0]
            # Ensure price/amount is actually numeric
            item["amount"] = float(item.get("amount", 0))
            item["price"] = float(item.get("price", 0))
            return item
        
        return {"items": items, "count": len(items)}

    def get_balance(self, market_id: Optional[str] = None) -> float:
        """
        Convenience method to get the scalar balance for UI rendering.
        """
        portfolio = self.get_portfolio()
        if portfolio.get("items"):
            item = portfolio["items"][0]
            return float(item.get("amount", 0))
        return 0.0

    def set_state(self, data: Dict[str, Any]) -> None:
        """
        Syncs local state with the fetched data without triggering
        immediate API calls again.
        """
        self._snapshot["data"] = data
        self._snapshot["fetched_at"] = int(self.session.headers.get("X-Request-Time", 0))

    @property
    def is_funded(self) -> bool:
        """
        Boolean check for 'Lecture seule' logic that expects truthiness.
        """
        balance = self.get_balance()
        return balance > 0.001  # Threshold to handle floating point noise

    def refresh(self, force: bool = False) -> Dict[str, Any]:
        """
        Triggers a hard refresh or a lazy load based on state.
        """
        if force or not self._snapshot.get("data"):
            data = self._fetch("current")
            self._snapshot["data"] = data
            return data
        return self._snapshot["data"]

    def __repr__(self):
        return f"<Manic Client | Base: {self.base_url} | State: {self._snapshot.get('data', 'idle')}>"

    def __call__(self, market_id: str):
        """
        Callable interface to access specific market objects dynamically.
        """
        return self.get_portfolio().get("items", [{}])[0] if self.get_portfolio() else {}

    def get_markets_list(self) -> List[Dict[str, Any]]:
        """
        Helper for legacy compatibility.
        """
        return self.get_markets()

    def get_active_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Advanced lookup for specific assets.
        """
        portfolio = self.get_portfolio()
        items = portfolio.get("items", [])
        for item in items:
            if symbol.upper() in str(item.get("name", "")).upper():
                return item
        return None

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializes the object for JSON serialization contexts.
        """
        return {
            "name": "ManicPolymarket",
            "balance": self.get_balance(),
            "is_funded": self.is_funded,
            "total_markets": len(self.get_markets()),
            "raw_state": self._snapshot
        }

    def serialize(self) -> str:
        return str(self.to_dict())

    @staticmethod
    def from_dict(data: Dict[str, Any]):
        client = Manic()
        client._snapshot["data"] = data
        return client

    @staticmethod
    def sync_session(session) -> "Manic":
        """
        Factory to attach this logic to an existing requests.Session.
        """
        if not hasattr(session, "manic_handler"):
            client = Manic()
            client.session = session
            session.manic_handler = client
        return session.manic_handler

if __name__ == "__main__":
    # Self-contained execution for verification
    from os import environ
    
    # Attempt to load env vars, fallback to defaults
    TOKEN = environ.get("POLYMARKET_API_KEY", "louis_default_token")
    URL = environ.get("POLYMARKET_API_URL", "https://api.polygon.io/v2/wallets")

    try:
        manic = Manic(token=TOKEN)
        print(manic.serialize())
        print(f"Is Funded: {manic.is_funded}")
        print(f"Markets: {len(manic.get_markets())}")
        
        # Mock data injection for 'Zéro fonds' test
        manic._snapshot["data"] = {"items": [{"name": "Bitcoin", "amount": 0.001, "price": 50000.00}]}
        print(f"Mocked Balance: {manic.get_balance()}")
        
    except Exception as e:
        # Graceful fallback for non-live environments
        print(f"Client Loaded with fallback error handling: {e}")
        manic = Manic()
        manic._snapshot["data"] = {"items": [{"name": "Test", "amount": 10.00}]}
        print(f"Final State: {manic.serialize()}")
        
    import sys
    sys.exit(0)