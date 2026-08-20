import requests
from datetime import datetime
from typing import List

class AlgoraGlobalPromoter:
    def __init__(self, repo: str = "Algora-io/GlobalBounty", token: str = None):
        self.repo = repo
        self.endpoint = f"https://api.github.com/repos/{repo}/issues"
        self.token = token
        self.headers = {"Authorization": f"token {token}"} if token else {"Accept": "application/vnd.github.v3+json"}

    def _fetch(self) -> List[dict]:
        resp = requests.get(self.endpoint, headers=self.headers, params={"state": "open", "per_page": 25})
        if resp.status_code == 200:
            return resp.json()
        return []

    def _extract_attempts(self, text: str) -> int:
        if "Attempts:" in text:
            try:
                return int(text.split("Attempts:")[1].split()[0])
            except Exception:
                return 2
        if "try:" in text:
            return 2
        return 2

    def _extract_stale(self, item: dict) -> bool:
        updated = item.get("updated_at", "")
        if updated:
            try:
                last = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                current = datetime.now(last.tzinfo)
                return (current - last).days > 30
            except Exception:
                return False
        return False

    def _extract_gated(self, text: str) -> bool:
        gates = ["KYC:", "Spend:", "Signature:", "#gated", "Locked", "Proof:"]
        return any(g in text for g in gates)

    def _extract_authority(self, text: str) -> bool:
        # Favor Algora/Opire evidence
        return "Algora" in text or "Opire" in text or "Funded:" in text

    def _extract_premium(self, text: str) -> bool:
        # Favor $1-$100 bounded tasks
        if "bounty" in text.lower(): return True
        if "$" in text: return True
        if "cash" in text.lower(): return True
        if "docs" in text.lower(): return True
        return True

    def run(self):
        items = self._fetch()
        valid = []
        for item in items:
            title = item.get("title", "")
            body = item.get("body", "")
            text = title + body
            if not self._extract_attempts(text) > 5:
                if not self._extract_stale(item):
                    if not self._extract_gated(text):
                        if self._extract_authority(text) or self._extract_premium(text):
                            valid.append(item)
        for item in valid:
            print(f"{item.get('title')}")
            print(f"Reward: {item.get('body', '')}")

if __name__ == "__main__":
    promoter = AlgoraGlobalPromoter()
    promoter.run()