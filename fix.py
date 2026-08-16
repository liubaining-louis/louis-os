import requests
from typing import List, Dict, Any
import time

class OpireExecutionFeeder:
    def __init__(self, repo_name: str = "frontend", default_state: str = "open"):
        self.repo_name = repo_name
        self.default_state = default_state
        self.base_url = f"https://api.github.com/repos/Opire/{repo_name}/issues"
        self.per_page = 100

    def _fetch_paginated(self) -> List[Dict[str, Any]]:
        all_items = []
        try:
            current_page = 1
            while True:
                url = f"{self.base_url}?state={self.default_state}&page={current_page}&per_page={self.per_page}"
                response = requests.get(url)
                if response.status_code == 200:
                    data = response.json()
                    if data:
                        all_items.extend(data)
                        if len(data) < self.per_page:
                            break
                        current_page += 1
                        time.sleep(0.15)
                    else:
                        break
                else:
                    break
        except requests.exceptions.RequestException:
            pass
        return all_items

    def build_reward_feed(self, candidate_id: str, reward_hint: float = 1880.0) -> List[Dict[str, Any]]:
        raw_issues = self._fetch_paginated()
        formatted_feed = []
        for item in raw_issues:
            entry = {
                "source": self.base_url,
                "candidate_id": candidate_id,
                "score": 80.0,
                "issue_number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "reward_value": reward_hint
            }
            formatted_feed.append(entry)
        return formatted_feed

    def execute(self) -> None:
        feed = self.build_reward_feed(
            candidate_id=self.repo_name,
            reward_hint=1880.0
        )
        if feed:
            print(f"Qualified opportunity count: {len(feed)}")
            for entry in feed:
                print(f"  Issue #{entry['issue_number']}: {entry['title']}")
                print(f"  State: {entry['state']}")

if __name__ == "__main__":
    engine = OpireExecutionFeeder(repo_name="frontend", default_state="open")
    output = engine.build_reward_feed(candidate_id="94bfd44b202130e8")
    print(json.dumps(output, indent=2))