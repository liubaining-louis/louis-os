const { EventEmitter } = require('events');

class CIMonitor extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.interval = null;
    this.monitoredPRs = new Map();
  }

  start() {
    if (this.interval) return;
    
    this.interval = setInterval(() => {
      this.checkAllPRs();
    }, this.config.pollInterval || 60000);
  }

  stop() {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
  }

  monitorPR(prUrl) {
    this.monitoredPRs.set(prUrl, {
      startTime: Date.now(),
      checks: []
    });
  }

  async checkAllPRs() {
    for (const [prUrl, metadata] of this.monitoredPRs.entries()) {
      try {
        const status = await this.checkPRStatus(prUrl);
        metadata.checks.push({
          timestamp: new Date().toISOString(),
          status
        });
        
        this.emit('ci-update', { prUrl, status });
        
        if (this.isComplete(status)) {
          this.monitoredPRs.delete(prUrl);
          this.emit('ci-complete', { prUrl, status });
        }
      } catch (e) {
        console.error(`Error checking ${prUrl}:`, e.message);
      }
    }
  }

  async checkPRStatus(prUrl) {
    // Parse PR URL to get owner, repo, and PR number
    const match = prUrl.match(/github\.com\/([^/]+)\/([^/]+)\/pull\/(\d+)/);
    if (!match) {
      return { state: 'error', reason: 'Invalid PR URL' };
    }

    const [, owner, repo, prNumber] = match;
    
    // Get PR details
    const { data: pr } = await this.config.octokit.request(
      'GET /repos/{owner}/{repo}/pulls/{pull_number}',
      { owner, repo, pull_number: parseInt(prNumber) }
    );

    // Get status checks
    const { data: checks } = await this.config.octokit.request(
      'GET /repos/{owner}/{repo}/commits/{commit_sha}/check-runs',
      { owner, repo, commit_sha: pr.head.sha }
    ).catch(() => ({ data: { items: [] } }));

    return {
      state: pr.state,
      merged: pr.merged_at !== null,
      checks: checks.items.map(c => ({
        name: c.name,
        status: c.status,
        conclusion: c.conclusion
      }))
    };
  }

  isComplete(status) {
    return status.state === 'closed' || 
           (status.checks && status.checks.some(c => c.conclusion === 'success'));
  }

  async diagnoseFailure(checkResult) {
    return {
      failure: checkResult.conclusion,
      details: checkResult.output?.summary,
      recommendation: this.getRecommendation(checkResult)
    };
  }

  getRecommendation(checkResult) {
    switch (checkResult.conclusion) {
      case 'failure':
        return 'Review test output and fix the failing test';
      case 'timed_out':
        return 'Check for infinite loops or long-running operations';
      case 'cancelled':
        return 'Check for conflicts or retry the build';
      default:
        return 'Review the check logs for more details';
    }
  }
}

module.exports = { CIMonitor };
