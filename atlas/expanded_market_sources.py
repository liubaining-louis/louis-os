"""Expanded, read-only public source mesh for bounded cash-first missions.

These adapters broaden category coverage while reusing the existing fail-closed
budget, competition, effort, identity, safety and platform-payment filters.
Discovery never creates an account or submits a proposal.
"""
from __future__ import annotations

from .simple_mission_sources import FreelancerPublicJobsSource
from .software_micro_missions import SoftwareFreelancerPublicJobsSource


class ExpandedFreelancerPublicJobsSource(FreelancerPublicJobsSource):
    """Broader simple-digital coverage on official Freelancer category pages."""

    source_id = "freelancer_public_expanded_simple_jobs"
    category_urls = (
        "https://www.freelancer.com/jobs/data-entry/",
        "https://www.freelancer.com/jobs/data-processing/",
        "https://www.freelancer.com/jobs/web-search/",
        "https://www.freelancer.com/jobs/internet-research/",
        "https://www.freelancer.com/jobs/market-research/",
        "https://www.freelancer.com/jobs/lead-generation/",
        "https://www.freelancer.com/jobs/excel/",
        "https://www.freelancer.com/jobs/google-sheets/",
        "https://www.freelancer.com/jobs/research-writing/",
        "https://www.freelancer.com/jobs/technical-writing/",
        "https://www.freelancer.com/jobs/content-writing/",
        "https://www.freelancer.com/jobs/copywriting/",
        "https://www.freelancer.com/jobs/translation/",
        "https://www.freelancer.com/jobs/french-translator/",
        "https://www.freelancer.com/jobs/english-translation/",
        "https://www.freelancer.com/jobs/proofreading/",
        "https://www.freelancer.com/jobs/editing/",
        "https://www.freelancer.com/jobs/documentation/",
    )


class ExpandedSoftwareFreelancerPublicJobsSource(SoftwareFreelancerPublicJobsSource):
    """Broader narrow software coverage, still limited to tested <=16 h scopes."""

    source_id = "freelancer_public_expanded_software_jobs"
    category_urls = (
        "https://www.freelancer.com/jobs/website-design/",
        "https://www.freelancer.com/jobs/html/",
        "https://www.freelancer.com/jobs/css/",
        "https://www.freelancer.com/jobs/javascript/",
        "https://www.freelancer.com/jobs/frontend-development/",
        "https://www.freelancer.com/jobs/wordpress/",
        "https://www.freelancer.com/jobs/elementor/",
        "https://www.freelancer.com/jobs/python/",
        "https://www.freelancer.com/jobs/scripting/",
        "https://www.freelancer.com/jobs/automation/",
        "https://www.freelancer.com/jobs/api/",
        "https://www.freelancer.com/jobs/rest-api/",
        "https://www.freelancer.com/jobs/software-testing/",
        "https://www.freelancer.com/jobs/website-testing/",
    )
