import { context, getOctokit } from '@actions/github';
import { getInput, setFailed, info } from '@actions/core';

/**
 * Validates that a draft pull request contains at least one file change.
 * If the PR is a draft and has no changes, it will be closed with a comment.
 */
export async function run(): Promise<void> {
  try {
    const token = getInput('github-token', { required: true });
    const octokit = getOctokit(token);
    const { owner, repo } = context.repo;
    const prNumber = context.issue.number;

    // Get PR details
    const { data: pr } = await octokit.pulls.get({
      owner,
      repo,
      pull_number: prNumber,
    });

    // Skip non-draft PRs
    if (!pr.draft) {
      info(`PR #${prNumber} is not a draft. Skipping validation.`);
      return;
    }

    // List changed files
    const { data: files } = await octokit.pulls.listFiles({
      owner,
      repo,
      pull_number: prNumber,
      per_page: 100,
    });

    if (files.length === 0) {
      // No changes – close the PR with a helpful comment
      await octokit.issues.createComment({
        owner,
        repo,
        issue_number: prNumber,
        body: '⚠️ This draft does not contain any file changes. Please add a patch or remove the draft status.',
      });

      await octokit.pulls.update({
        owner,
        repo,
        pull_number: prNumber,
        state: 'closed',
      });

      info(`Closed draft PR #${prNumber} due to no changes.`);
      return;
    }

    info(`Draft PR #${prNumber} contains changes. Validation passed.`);
  } catch (error) {
    setFailed(`Validation failed: ${error}`);
  }
}

// Execute when run as a GitHub Action
if (require.main === module) {
  run();
}
