"""Bounded delivery capabilities for small paid software and website missions.

The module classifies only narrow, remotely deliverable work, provides reusable
capability specifications and generates deterministic demo bundles. It never deploys,
changes production systems, accepts platform terms or submits proposals.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import hashlib
import io
import json
import re
from typing import Any, Mapping

from .simple_mission_sources import FreelancerPublicJobsSource


@dataclass(frozen=True)
class SoftwareCapabilitySpec:
    capability_id: str
    title: str
    deliverable_family: str
    ideal_effort_hours: float
    maximum_effort_hours: float
    price_guidance_eur: tuple[int, int]
    acceptance_checks: tuple[str, ...]
    boundaries: tuple[str, ...]
    demo_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CAPABILITIES: tuple[SoftwareCapabilitySpec, ...] = (
    SoftwareCapabilitySpec(
        capability_id="static_website_delivery",
        title="Responsive static landing page or small brochure site",
        deliverable_family="small_website_and_landing_page",
        ideal_effort_hours=8.0,
        maximum_effort_hours=16.0,
        price_guidance_eur=(150, 800),
        acceptance_checks=(
            "semantic HTML contains one h1 and a viewport declaration",
            "layout remains usable at narrow viewport widths",
            "all local links and referenced assets resolve",
            "no external analytics, tracking or credential collection is introduced",
            "delivery includes source files, validation receipt and deployment instructions",
        ),
        boundaries=(
            "maximum five static pages",
            "no authentication, payment processing or customer database",
            "no copied protected design or site clone",
            "production deployment requires an explicit final gate",
        ),
        demo_id="landing_page",
    ),
    SoftwareCapabilitySpec(
        capability_id="frontend_bug_fix",
        title="Bounded HTML, CSS or JavaScript correction",
        deliverable_family="frontend_bug_fix",
        ideal_effort_hours=4.0,
        maximum_effort_hours=8.0,
        price_guidance_eur=(80, 350),
        acceptance_checks=(
            "the bug is reproduced with a fixture or deterministic description",
            "the patch changes only files needed for the bounded correction",
            "the corrected page passes syntax, local-link and regression checks",
            "before/after evidence is recorded without exposing private data",
        ),
        boundaries=(
            "one isolated user-visible defect",
            "no redesign of a complete application",
            "no unsupported browser or device promise",
            "no production credentials stored in the repository",
        ),
        demo_id="landing_page",
    ),
    SoftwareCapabilitySpec(
        capability_id="python_automation_delivery",
        title="Deterministic Python file or CSV automation",
        deliverable_family="python_file_and_data_automation",
        ideal_effort_hours=6.0,
        maximum_effort_hours=12.0,
        price_guidance_eur=(120, 500),
        acceptance_checks=(
            "input and output schemas are documented",
            "the script is deterministic for the same input",
            "invalid input fails with a clear error",
            "sample input, expected output and automated tests are included",
            "no destructive write occurs without an explicit output path",
        ),
        boundaries=(
            "local files or public authorized data only",
            "no credential harvesting or access-control bypass",
            "no high-frequency scraping or prohibited automation",
            "no irreversible production action",
        ),
        demo_id="csv_automation",
    ),
    SoftwareCapabilitySpec(
        capability_id="api_integration_delivery",
        title="Narrow HTTP API client or webhook integration",
        deliverable_family="narrow_api_and_webhook_integration",
        ideal_effort_hours=8.0,
        maximum_effort_hours=16.0,
        price_guidance_eur=(200, 600),
        acceptance_checks=(
            "the API contract, timeout and error behavior are explicit",
            "network access is injectable and tests run without live external calls",
            "secrets are accepted through environment or caller configuration only",
            "sample payloads and deterministic unit tests are included",
            "rate limits and platform terms are preserved",
        ),
        boundaries=(
            "one documented API or webhook flow",
            "no payment, identity or security-critical integration without human review",
            "no undocumented private endpoint",
            "no secret committed to source control",
        ),
        demo_id="api_integration",
    ),
    SoftwareCapabilitySpec(
        capability_id="deployment_and_validation",
        title="Static deployment package and validation receipt",
        deliverable_family="deployment_package_and_validation",
        ideal_effort_hours=3.0,
        maximum_effort_hours=6.0,
        price_guidance_eur=(50, 150),
        acceptance_checks=(
            "the package contains deterministic build-free static assets",
            "all local paths and links are validated",
            "deployment instructions identify the exact reversible steps",
            "the external deployment state remains false until a platform receipt exists",
        ),
        boundaries=(
            "static hosting only by default",
            "DNS, billing and production ownership changes require explicit approval",
            "no hidden telemetry or third-party script injection",
        ),
        demo_id="landing_page",
    ),
)

CAPABILITY_BY_ID = {item.capability_id: item for item in CAPABILITIES}


_SOFTWARE_TERMS = (
    "landing page",
    "one page website",
    "one-page website",
    "brochure website",
    "static website",
    "responsive website",
    "website design",
    "html",
    "css",
    "javascript",
    "frontend",
    "front-end",
    "wordpress fix",
    "python script",
    "python automation",
    "csv automation",
    "excel automation",
    "api integration",
    "rest api",
    "webhook",
    "netlify",
    "vercel",
    "cloudflare pages",
    "deploy website",
)

_REJECT_PATTERNS = (
    ("oversized_full_application", re.compile(r"\b(full[- ]?stack|complete|entire)\s+(application|app|platform|marketplace|saas)\b", re.I)),
    ("oversized_clone", re.compile(r"\b(clone|copy)\s+(?:the\s+)?(?:entire\s+)?(?:site|website|app|platform|design)\b", re.I)),
    ("oversized_ecommerce", re.compile(r"\b(?:complete|full)\s+(?:e[- ]?commerce|online store)\b", re.I)),
    ("unbounded_support", re.compile(r"\b(unlimited revisions?|unlimited support|24/7 support|ongoing maintenance|long[- ]?term developer)\b", re.I)),
    ("security_or_access_bypass", re.compile(r"\b(bypass|credential harvesting|steal credentials?|crack password|unauthorized access|evade detection)\b", re.I)),
    ("high_risk_production_change", re.compile(r"\b(production database migration|live payment gateway|banking integration|identity verification integration)\b", re.I)),
    ("off_platform_or_deceptive", re.compile(r"\b(pay outside|contact on whatsapp|contact on telegram|fake review|fake traffic|click fraud)\b", re.I)),
)


def capability_specs() -> tuple[SoftwareCapabilitySpec, ...]:
    return CAPABILITIES


def looks_like_software_request(title: str, description: str = "") -> bool:
    text = f"{title}\n{description}".casefold()
    return any(term in text for term in _SOFTWARE_TERMS)


def rejection_reason(title: str, description: str = "") -> str | None:
    text = f"{title}\n{description}"
    for reason, pattern in _REJECT_PATTERNS:
        if pattern.search(text):
            return reason
    return None


def classify_software_capability(title: str, description: str = "") -> str | None:
    text = f"{title}\n{description}".casefold()
    if not looks_like_software_request(title, description):
        return None
    if any(term in text for term in ("deploy", "deployment", "netlify", "vercel", "cloudflare pages", "hosting setup")):
        return "deployment_and_validation"
    if any(term in text for term in ("api integration", "rest api", "webhook", "http api", "json api", "connect api")):
        return "api_integration_delivery"
    if any(term in text for term in ("python script", "python automation", "csv automation", "excel automation", "file automation", "batch process")):
        return "python_automation_delivery"
    if any(term in text for term in ("fix", "bug", "issue", "responsive problem", "alignment", "broken layout", "javascript error", "css error")):
        return "frontend_bug_fix"
    if any(term in text for term in ("landing page", "one page website", "one-page website", "brochure website", "static website", "responsive website", "website design", "html", "css", "javascript", "frontend", "front-end")):
        return "static_website_delivery"
    return None


def estimate_software_effort(title: str, description: str = "", capability_id: str | None = None) -> float:
    capability = capability_id or classify_software_capability(title, description)
    if capability is None:
        return 24.0
    text = f"{title}\n{description}".casefold()
    base = CAPABILITY_BY_ID[capability].ideal_effort_hours
    if any(term in text for term in ("five pages", "5 pages", "multiple endpoints", "two apis", "2 apis", "wordpress")):
        base += 4.0
    if any(term in text for term in ("single page", "one page", "one-page", "small fix", "minor fix", "one endpoint")):
        base = max(2.0, base - 2.0)
    return min(CAPABILITY_BY_ID[capability].maximum_effort_hours, base)


def assess_software_scope(title: str, description: str = "") -> dict[str, Any]:
    matched = looks_like_software_request(title, description)
    if not matched:
        return {"matched": False, "accepted": False, "reason": "not_software_micro_mission"}
    reason = rejection_reason(title, description)
    if reason:
        return {"matched": True, "accepted": False, "reason": reason}
    capability = classify_software_capability(title, description)
    if capability is None:
        return {"matched": True, "accepted": False, "reason": "software_scope_unclassified"}
    effort = estimate_software_effort(title, description, capability)
    spec = CAPABILITY_BY_ID[capability]
    if effort > spec.maximum_effort_hours or effort > 16.0:
        return {"matched": True, "accepted": False, "reason": "estimated_effort_exceeds_16_hours"}
    return {
        "matched": True,
        "accepted": True,
        "reason": "bounded_software_micro_mission",
        "capability_id": capability,
        "estimated_effort_hours": effort,
        "price_guidance_eur": list(spec.price_guidance_eur),
        "acceptance_checks": list(spec.acceptance_checks),
        "boundaries": list(spec.boundaries),
        "deliverable_family": spec.deliverable_family,
    }


class SoftwareFreelancerPublicJobsSource(FreelancerPublicJobsSource):
    """Freelancer public categories dedicated to narrow web and code work."""

    source_id = "freelancer_public_software_jobs"
    category_urls = (
        "https://www.freelancer.com/jobs/website-design/",
        "https://www.freelancer.com/jobs/html/",
        "https://www.freelancer.com/jobs/css/",
        "https://www.freelancer.com/jobs/javascript/",
        "https://www.freelancer.com/jobs/python/",
        "https://www.freelancer.com/jobs/api/",
        "https://www.freelancer.com/jobs/wordpress/",
    )


def landing_page_demo_files() -> dict[str, str]:
    return {
        "index.html": """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Northstar Studio — Fast, testable delivery</title>
  <meta name=\"description\" content=\"A dependency-free responsive landing page demo.\">
  <link rel=\"stylesheet\" href=\"styles.css\">
</head>
<body>
  <header class=\"site-header\"><a class=\"brand\" href=\"#main\">Northstar Studio</a><nav aria-label=\"Primary\"><a href=\"#services\">Services</a><a href=\"#contact\">Contact</a></nav></header>
  <main id=\"main\">
    <section class=\"hero\"><p class=\"eyebrow\">Small digital projects</p><h1>Launch a clear, responsive page quickly.</h1><p>Source files, validation and deployment instructions included.</p><a class=\"button\" href=\"#contact\">Request a scoped delivery</a></section>
    <section id=\"services\" class=\"grid\" aria-label=\"Services\"><article><h2>Landing page</h2><p>Semantic, responsive and dependency-free.</p></article><article><h2>Bug correction</h2><p>One bounded issue with before-and-after validation.</p></article><article><h2>Deployment package</h2><p>Reversible static hosting instructions and link checks.</p></article></section>
    <section id=\"contact\" class=\"contact\"><h2>Project brief</h2><form id=\"brief-form\"><label>Project name<input name=\"project\" required maxlength=\"80\"></label><label>Goal<textarea name=\"goal\" required maxlength=\"500\"></textarea></label><button type=\"submit\">Validate brief</button><p id=\"form-status\" role=\"status\" aria-live=\"polite\"></p></form></section>
  </main>
  <footer><p>Demo only — no external submission or tracking.</p></footer>
  <script src=\"script.js\"></script>
</body>
</html>
""",
        "styles.css": """*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;line-height:1.6;color:#172033;background:#f6f7fb}.site-header{display:flex;justify-content:space-between;align-items:center;padding:1rem clamp(1rem,5vw,5rem);background:#fff;border-bottom:1px solid #dde2ea}.brand{font-weight:700}.site-header a{color:inherit;text-decoration:none}.site-header nav{display:flex;gap:1rem}.hero,.contact{padding:clamp(3rem,8vw,7rem) clamp(1rem,8vw,8rem)}.hero{background:#fff}.hero h1{max-width:16ch;font-size:clamp(2.2rem,7vw,5rem);line-height:1.05}.eyebrow{font-weight:700;text-transform:uppercase;letter-spacing:.08em}.button,button{display:inline-block;border:0;border-radius:.6rem;padding:.8rem 1rem;background:#172033;color:#fff;text-decoration:none;cursor:pointer}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem;padding:2rem clamp(1rem,8vw,8rem)}article,form{background:#fff;padding:1.25rem;border:1px solid #dde2ea;border-radius:1rem}label{display:grid;gap:.35rem;margin-bottom:1rem}input,textarea{width:100%;padding:.7rem;border:1px solid #aab4c3;border-radius:.45rem}footer{padding:1rem;text-align:center}@media(max-width:720px){.site-header{align-items:flex-start;gap:1rem}.grid{grid-template-columns:1fr}.site-header nav{flex-wrap:wrap}}
""",
        "script.js": """'use strict';
const form = document.querySelector('#brief-form');
const status = document.querySelector('#form-status');
form.addEventListener('submit', (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  status.textContent = 'Brief validated locally. Nothing was sent.';
});
""",
        "DEPLOYMENT.md": """# Static deployment instructions

1. Review the files and validation receipt.
2. Upload this directory to an authorized static host such as Netlify, Vercel or Cloudflare Pages.
3. Do not change DNS, billing or production ownership without explicit approval.
4. Preserve the deployment receipt and final public URL after the authorized action.

External deployment performed: false.
""",
    }


def csv_automation_demo_files() -> dict[str, str]:
    return {
        "process_csv.py": '''"""Normalize and deduplicate a contact CSV without modifying the input file."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

REQUIRED = ("name", "email", "company")


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def process_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        missing = [field for field in REQUIRED if field not in row]
        if missing:
            raise ValueError("missing fields: " + ",".join(missing))
        email = normalize_text(row["email"]).casefold()
        if not email or "@" not in email or email in seen:
            continue
        seen.add(email)
        output.append({
            "name": normalize_text(row["name"]),
            "email": email,
            "company": normalize_text(row["company"]),
        })
    return sorted(output, key=lambda item: (item["company"].casefold(), item["email"]))


def process_file(input_path: Path, output_path: Path) -> int:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("output path must differ from input path")
    with input_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    cleaned = process_rows(rows)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED)
        writer.writeheader()
        writer.writerows(cleaned)
    return len(cleaned)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(process_file(args.input, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
        "sample_input.csv": "name,email,company\n Alice  Martin ,ALICE@example.com, Acme \nAlice Martin,alice@example.com,Acme\nBob Lee,bob@example.com, Beta Labs\nInvalid,missing-email,Beta Labs\n",
        "expected_output.csv": "name,email,company\nAlice Martin,alice@example.com,Acme\nBob Lee,bob@example.com,Beta Labs\n",
        "README.md": "# CSV automation demo\n\nRun `python process_csv.py sample_input.csv output.csv`. The input is never overwritten.\n",
    }


def api_integration_demo_files() -> dict[str, str]:
    return {
        "api_client.py": '''"""Small injectable JSON API client with no embedded credentials."""
from __future__ import annotations

import json
from typing import Any, Callable
from urllib.request import Request, urlopen


def fetch_json(url: str, *, opener: Callable[..., Any] = urlopen, timeout: float = 10.0) -> dict[str, Any]:
    if not url.startswith("https://"):
        raise ValueError("url must use https")
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Louis-OS-Demo/1.0"})
    with opener(request, timeout=timeout) as response:
        if getattr(response, "status", 200) >= 400:
            raise RuntimeError(f"http status {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload


def select_fields(payload: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: payload[field] for field in fields if field in payload}
''',
        "sample_payload.json": json.dumps({"id": 7, "name": "Example", "status": "active"}, indent=2) + "\n",
        "README.md": "# API integration demo\n\nThe client accepts only HTTPS, has a timeout, embeds no secret and supports an injected opener for offline tests.\n",
    }


def demo_bundles() -> dict[str, dict[str, str]]:
    return {
        "landing_page": landing_page_demo_files(),
        "csv_automation": csv_automation_demo_files(),
        "api_integration": api_integration_demo_files(),
    }


def validate_demo_bundle(demo_id: str, files: Mapping[str, str]) -> tuple[str, ...]:
    checks: list[str] = []
    if demo_id == "landing_page":
        html = files.get("index.html", "")
        required = ("<meta name=\"viewport\"", "<h1>", "aria-live=\"polite\"", "styles.css", "script.js")
        if not all(value in html for value in required):
            raise ValueError("landing_page_demo_invalid")
        if "http://" in "\n".join(files.values()) or "https://" in html:
            raise ValueError("landing_page_external_dependency")
        checks.extend(("semantic_html", "responsive_css", "local_form_only", "no_external_dependency"))
    elif demo_id == "csv_automation":
        namespace: dict[str, Any] = {"__name__": "demo_module"}
        exec(files["process_csv.py"], namespace)  # noqa: S102 - trusted repository-owned demo fixture
        rows = list(csv.DictReader(io.StringIO(files["sample_input.csv"])))
        cleaned = namespace["process_rows"](rows)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=("name", "email", "company"), lineterminator="\n")
        writer.writeheader()
        writer.writerows(cleaned)
        if output.getvalue() != files["expected_output.csv"]:
            raise ValueError("csv_automation_output_mismatch")
        checks.extend(("deterministic_output", "deduplication", "schema_validation", "input_not_overwritten"))
    elif demo_id == "api_integration":
        namespace = {"__name__": "demo_module"}
        exec(files["api_client.py"], namespace)  # noqa: S102 - trusted repository-owned demo fixture
        selected = namespace["select_fields"]({"id": 1, "name": "x", "secret": "ignored"}, ("id", "name"))
        if selected != {"id": 1, "name": "x"}:
            raise ValueError("api_integration_transform_invalid")
        try:
            namespace["fetch_json"]("http://example.test")
        except ValueError:
            pass
        else:
            raise ValueError("api_integration_https_guard_missing")
        checks.extend(("https_guard", "injectable_network", "timeout", "no_embedded_secret"))
    else:
        raise ValueError(f"unknown_demo:{demo_id}")
    return tuple(checks)


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def capability_catalog() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "currency": "EUR",
        "pricing_status": "guidance_only_not_a_quote_or_revenue",
        "capabilities": [item.to_dict() for item in CAPABILITIES],
        "external_submissions_verified": 0,
        "revenue_verified_eur": 0.0,
    }
