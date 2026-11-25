#!/usr/bin/env python3
"""
Global Cash Promoter Service
Discovers bounty tasks, verifies authoritative payouts, filters based on competition and safety,
and maintains a shortlist of 8-10 safe candidates.
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import requests
from github import Github
from github.GithubException import GithubException

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
MAX_SHORTLIST_SIZE = 10
MIN_SHORTLIST_SIZE = 8
MAX_ACTIVE_ATTEMPTS = 5
MIN_REWARD = 1
MAX_REWARD = 100
SUPPORTED_LANGUAGES = ['python', 'javascript', 'typescript', 'go', 'docs', 'data', 'research']
AUTHORIZED_PROVIDERS = ['algora', 'opire']

# GitHub API configuration
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_API = 'https://api.github.com'

# Initialize GitHub client
gh = Github(GITHUB_TOKEN)


def search_bounty_issues(query: str = '') -> List[Dict[str, Any]]:
    """Search GitHub for open bounty/reward issues."""
    try:
        # Search for issues with bounty keywords
        search_query = f'is:open is:issue label:bounty OR label:reward {query}'
        issues = gh.search_issues(search_query, sort='created', order='desc')
        
        bounty_issues = []
        for issue in issues[:100]:  # Limit to first 100 results
            bounty_issues.append({
                'id': issue.id,
                'number': issue.number,
                'title': issue.title,
                'url': issue.html_url,
                'repo': issue.repository.full_name,
                'created_at': issue.created_at.isoformat(),
                'updated_at': issue.updated_at.isoformat(),
                'body': issue.body,
                'labels': [label.name for label in issue.labels]
            })
            
        logger.info(f"Found {len(bounty_issues)} bounty issues")
        return bounty_issues
    except GithubException as e:
        logger.error(f"Error searching bounty issues: {e}")
        return []


def verify_authoritative_payout(issue: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Verify authoritative provider evidence in comments."""
    try:
        repo = gh.get_repo(issue['repo'])
        issue_obj = repo.get_issue(issue['number'])
        
        # Get all comments
        comments = []
        for comment in issue_obj.get_comments():
            comments.append({
                'id': comment.id,
                'body': comment.body,
                'created_at': comment.created_at.isoformat(),
                'author': comment.user.login if comment.user else None
            })
        
        # Look for authoritative payout evidence
        payout_info = {
            'verified': False,
            'provider': None,
            'amount': None,
            'currency': None,
            'receipt_url': None,
            'active_attempts': 0
        }
        
        # Check issue body and comments for payout evidence
        all_text = f"{issue['body']} {' '.join([c['body'] for c in comments])}"
        all_text_lower = all_text.lower()
        
        # Check for authorized providers
        for provider in AUTHORIZED_PROVIDERS:
            if provider in all_text_lower:
                payout_info['provider'] = provider
                payout_info['verified'] = True
                
                # Extract reward amount
                import re
                amount_match = re.search(r'\$?(\d+(?:\.\d{1,2})?)', all_text)
                if amount_match:
                    amount = float(amount_match.group(1))
                    payout_info['amount'] = amount
                    
                    # Assume USD if no currency specified
                    payout_info['currency'] = 'USD'
                    
                # Look for receipt URLs
                url_pattern = r'https?://\S+'
                urls = re.findall(url_pattern, all_text)
                for url in urls:
                    if 'receipt' in url or 'payment' in url or 'fund' in url:
                        payout_info['receipt_url'] = url
                        break
                
                # Count active attempts by looking for submission patterns
                attempt_patterns = [
                    r'(@|from)\s+\w+\s+(submitted|attempted|tried)',
                    r'(submission|attempt|try)\s+#?\d+',
                    r'(\w+)\s+(has|have)\s+(submitted|attempted)'
                ]
                
                for pattern in attempt_patterns:
                    matches = re.findall(pattern, all_text, re.IGNORECASE)
                    payout_info['active_attempts'] += len(matches)
                
                break
        
        return payout_info if payout_info['verified'] else None
        
    except GithubException as e:
        logger.error(f"Error verifying payout for issue {issue['number']}: {e}")
        return None


def is_safe_task(issue: Dict[str, Any], payout_info: Dict[str, Any]) -> bool:
    """Check if task is safe (not saturated, stale, unsafe, or KYC/gated)."""
    # Check for saturation
    if payout_info['active_attempts'] > MAX_ACTIVE_ATTEMPTS:
        logger.info(f"Task {issue['number']} saturated with {payout_info['active_attempts']} attempts")
        return False
    
    # Check for staleness (older than 30 days)
    updated_at = datetime.fromisoformat(issue['updated_at'].replace('Z', '+00:00'))
    if datetime.now(updated_at.tzinfo) - updated_at > timedelta(days=30):
        logger.info(f"Task {issue['number']} is stale")
        return False
    
    # Check for safety keywords
    unsafe_keywords = [
        'kyc', 'know your customer', 'identity verification', 'personal information',
        'deposit', 'payment required', 'fee', 'spend required', 'signature required',
        'private key', 'mnemonic', 'wallet connect'
    ]
    
    all_text = f"{issue['body']} {' '.join([c['body'] for c in issue.get('comments', [])])}"
    all_text_lower = all_text.lower()
    
    for keyword in unsafe_keywords:
        if keyword in all_text_lower:
            logger.info(f"Task {issue['number']} contains unsafe keyword: {keyword}")
            return False
    
    # Check for supported languages
    has_supported_language = False
    for label in issue['labels']:
        if any(lang in label.lower() for lang in SUPPORTED_LANGUAGES):
            has_supported_language = True
            break
    
    if not has_supported_language:
        logger.info(f"Task {issue['number']} doesn't have supported language/tech tags")
        return False
    
    # Check reward range
    if not (MIN_REWARD <= payout_info['amount'] <= MAX_REWARD):
        logger.info(f"Task {issue['number']} reward {payout_info['amount']} out of range {MIN_REWARD}-{MAX_REWARD}")
        return False
    
    return True


def filter_tasks(bounty_issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter tasks based on competition and safety criteria."""
    safe_tasks = []
    
    for issue in bounty_issues:
        logger.info(f"Verifying payout for issue {issue['number']}: {issue['title']}")
        payout_info = verify_authoritative_payout(issue)
        
        if payout_info and is_safe_task(issue, payout_info):
            task = {
                'id': issue['id'],
                'number': issue['number'],
                'title': issue['title'],
                'url': issue['url'],
                'repo': issue['repo'],
                'created_at': issue['created_at'],
                'updated_at': issue['updated_at'],
                'reward_amount': payout_info['amount'],
                'reward_currency': payout_info['currency'],
                'provider': payout_info['provider'],
                'receipt_url': payout_info['receipt_url'],
                'active_attempts': payout_info['active_attempts'],
                'labels': issue['labels']
            }
            safe_tasks.append(task)
            logger.info(f"Added safe task: {issue['title']} with reward {payout_info['amount']}")
        else:
            logger.info(f"Rejected task: {issue['title']}")
    
    # Sort by reward amount (descending)
    safe_tasks.sort(key=lambda x: x['reward_amount'], reverse=True)
    
    # Limit to shortlist size
    shortlist = safe_tasks[:MAX_SHORTLIST_SIZE]
    
    # Ensure minimum size
    if len(shortlist) < MIN_SHORTLIST_SIZE and len(safe_tasks) >= MIN_SHORTLIST_SIZE:
        shortlist = safe_tasks[:MIN_SHORTLIST_SIZE]
    
    logger.info(f"Generated shortlist with {len(shortlist)} tasks")
    return shortlist


def save_shortlist(shortlist: List[Dict[str, Any]]) -> None:
    """Save the shortlist to results/global_cash_shortlist.json."""
    os.makedirs('results', exist_ok=True)
    
    shortlist_data = {
        'generated_at': datetime.now().isoformat(),
        'shortlist': shortlist,
        'count': len(shortlist)
    }
    
    with open('results/global_cash_shortlist.json', 'w') as f:
        json.dump(shortlist_data, f, indent=2)
    
    logger.info(f"Saved shortlist with {len(shortlist)} tasks")


def main() -> None:
    """Main function to run the global cash promoter service."""
    logger.info("Starting Global Cash Promoter service")
    
    # Search for bounty issues
    bounty_issues = search_bounty_issues()
    
    if not bounty_issues:
        logger.warning("No bounty issues found")
        save_shortlist([])
        return
    
    # Filter tasks
    shortlist = filter_tasks(bounty_issues)
    
    # Save results
    save_shortlist(shortlist)
    
    logger.info("Global Cash Promoter service completed")


if __name__ == '__main__':
    main()
