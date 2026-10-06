const { Octokit } = require('octokit');

class PatchSubmissionEngine {
  constructor(config) {
    this.config = config;
    this.octokit = new Octokit({
      auth: config.githubToken,
      baseUrl: config.githubApiUrl || 'https://api.github.com'
    });
  }

  async inspectRepository() {
    const { data: repo } = await this.octokit.request('GET /repos/{owner}/{repo}', {
      owner: this.config.owner,
      repo: this.config.repo
    });

    const { data: contribDocs } = await this.octokit.request(
      'GET /repos/{owner}/{repo}/readme',
      { owner: this.config.owner, repo: this.config.repo }
    ).catch(() => ({ data: null }));

    return {
      name: repo.name,
      description: repo.description,
      hasContributingGuidelines: !!contribDocs,
      defaultBranch: repo.default_branch,
      fork: repo.fork,
      private: repo.private
    };
  }

  async buildSubmissionPlan(issueId) {
    const { data: issue } = await this.octokit.request(
      'GET /repos/{owner}/{repo}/issues/{issue_number}',
      { owner: this.config.owner, repo: this.config.repo, issue_number: issueId }
    );

    // Validate issue is relevant
    if (!this.isValidTargetIssue(issue)) {
      throw new Error(`Issue #${issueId} is not a valid target for patch submission`);
    }

    const plan = {
      issueId,
      title: issue.title,
      body: issue.body,
      labels: issue.labels.map(l => l.name),
      requiredFiles: this.extractRequiredFiles(issue),
      branchName: `patch/issue-${issueId}`,
      testCommand: this.extractTestCommand(issue),
      submitMethod: this.determineSubmitMethod(issue)
    };

    return plan;
  }

  isValidTargetIssue(issue) {
    // Reject generic drafts
    if (issue.pull_request) {
      return false;
    }
    
    // Must have proper labels or be in appropriate milestone
    const validLabels = ['bug', 'enhancement', 'good first issue', 'help wanted'];
    const hasValidLabel = issue.labels.some(l => validLabels.includes(l.name));
    
    return hasValidLabel || issue.state === 'open';
  }

  extractRequiredFiles(issue) {
    const files = [];
    const body = issue.body || '';
    
    // Parse body for file requirements
    const fileMatches = body.match(/\*\*Files?\*\*:\s*(.+?)(?:\n|$)/gi);
    if (fileMatches) {
      fileMatches.forEach(match => {
        const files_str = match.replace(/\*\*Files?\*\*:\s*/i, '').trim();
        files.push(...files_str.split(',').map(f => f.trim()));
      });
    }

    return files;
  }

  extractTestCommand(issue) {
    const body = issue.body || '';
    const match = body.match(/test[:\s]+(\S+)/i);
    return match ? match[1] : 'npm test';
  }

  determineSubmitMethod(issue) {
    // Check if we have push access
    if (this.config.hasPushAccess) {
      return 'direct-push';
    }
    return 'fork-and-pr';
  }

  async executePatch(plan) {
    let result;

    if (plan.submitMethod === 'direct-push') {
      result = await this.directPush(plan);
    } else {
      result = await this.forkAndPR(plan);
    }

    return result;
  }

  async directPush(plan) {
    // Create branch and commit
    const branch = await this.createBranch(plan.branchName);
    await this.commitChanges(plan, branch);
    
    return {
      type: 'direct-push',
      branch: branch.name,
      commitSha: branch.commitSha
    };
  }

  async forkAndPR(plan) {
    // Create or reuse fork
    const fork = await this.getOrCreateFork();
    
    // Create branch in fork
    const branch = await this.createBranchInFork(fork, plan.branchName);
    
    // Push changes
    const pushResult = await this.pushToBranch(branch);
    
    // Create PR
    const pr = await this.createPR(fork, branch, plan);
    
    return {
      type: 'fork-and-pr',
      fork: fork.html_url,
      branch: branch.name,
      prUrl: pr.html_url,
      prNumber: pr.number
    };
  }

  async createBranch(branchName) {
    const defaultBranch = this.config.defaultBranch || 'main';
    
    // Get default branch ref
    const { data: ref } = await this.octokit.request(
      'GET /repos/{owner}/{repo}/git/refs/heads/{branch}',
      { owner: this.config.owner, repo: this.config.repo, branch: defaultBranch }
    );

    // Create new branch
    const { data: newRef } = await this.octokit.request(
      'POST /repos/{owner}/{repo}/git/refs',
      {
        owner: this.config.owner,
        repo: this.config.repo,
        ref: `refs/heads/${branchName}`,
        sha: ref.object.sha
      }
    );

    return { name: branchName, sha: newRef.object.sha };
  }

  async createBranchInFork(fork, branchName) {
    const defaultBranch = fork.default_branch || 'main';
    
    const { data: ref } = await this.octokit.request(
      'GET /repos/{owner}/{repo}/git/refs/heads/{branch}',
      { owner: fork.owner.login, repo: fork.name, branch: defaultBranch }
    );

    const { data: newRef } = await this.octokit.request(
      'POST /repos/{owner}/{repo}/git/refs',
      {
        owner: fork.owner.login,
        repo: fork.name,
        ref: `refs/heads/${branchName}`,
        sha: ref.object.sha
      }
    );

    return { name: branchName, sha: newRef.object.sha, repo: fork.full_name };
  }

  async getOrCreateFork() {
    // Check if fork already exists
    try {
      const { data: fork } = await this.octokit.request(
        'GET /repos/{owner}/{repo}',
        { owner: this.config.githubUser, repo: this.config.repo }
      );
      return fork;
    } catch (e) {
      // Fork doesn't exist, create it
      const { data: fork } = await this.octokit.request(
        'POST /repos/{owner}/{repo}/forks',
        { owner: this.config.owner, repo: this.config.repo }
      );
      return fork;
    }
  }

  async commitChanges(plan, branch) {
    // Placeholder for actual file commit logic
    return { message: 'Auto-generated patch', sha: branch.sha };
  }

  async pushToBranch(branch) {
    // Placeholder for actual push logic
    return { committed: true, sha: branch.sha };
  }

  async createPR(fork, branch, plan) {
    const { data: pr } = await this.octokit.request(
      'POST /repos/{owner}/{repo}/pulls',
      {
        owner: fork.owner.login,
        repo: fork.name,
        title: `Fix: ${plan.title}`,
        body: this.buildPRBody(plan),
        head: `${fork.owner.login}:${branch.name}`,
        base: fork.default_branch
      }
    );
    return pr;
  }

  buildPRBody(plan) {
    return `## Summary\n\n${plan.body}\n\n## Changes\n\n- Implements fix for #${plan.issueId}\n\n## Testing\n\n- [ ] Tests pass\n\nCloses #${plan.issueId}`;
  }

  async listPendingIssues() {
    const { data: issues } = await this.octokit.request(
      'GET /repos/{owner}/{repo}/issues',
      { owner: this.config.owner, repo: this.config.repo, state: 'open' }
    );

    return issues
      .filter(i => !i.pull_request && this.isValidTargetIssue(i))
      .slice(0, 10)
      .map(i => ({ id: i.number, title: i.title }));
  }
}

module.exports = { PatchSubmissionEngine };
