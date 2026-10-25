/**
 * autonomous-patch.ts
 *
 * A self‑contained CLI tool that:
 *   1. Validates that a given GitHub issue is a patch request.
 *   2. Inspects repository metadata and contribution rules.
 *   3. Generates a deterministic submission plan.
 *   4. Applies the patch, runs tests, and creates a PR (or pushes directly if allowed).
 *
 * Usage:
 *   npx ts-node autonomous-patch.ts \
 *       --repo owner/repo \
 *       --issue 123 \
 *       --token $GITHUB_TOKEN \
 *       --patch ./patch.diff
 *
 * Environment:
 *   GITHUB_TOKEN – a personal access token with repo scope.
 *
 * Dependencies (install with npm):
 *   npm i @octokit/rest simple-git yargs
 */

import { Octokit } from "@octokit/rest";
import simpleGit, { SimpleGit } from "simple-git";
import * as fs from "fs";
import * as path from "path";
import { execSync } from "child_process";
import yargs from "yargs";
import { hideBin } from "yargs/helpers";

interface RepoInfo {
  owner: string;
  name: string;
  defaultBranch: string;
  cloneUrl: string;
  hasPushAccess: boolean;
  contributionFile?: string;
}

interface IssueInfo {
  number: number;
  title: string;
  body: string;
  labels: string[];
  author: string;
  isPatchRequest: boolean;
}

interface SubmissionPlan {
  filesToModify: string[];
  testsToRun: string[];
  branchName: string;
  commitMessage: string;
}

/* ---------- CLI ---------- */
const argv = yargs(hideBin(process.argv))
  .option("repo", { type: "string", demandOption: true, describe: "GitHub repo in owner/name format" })
  .option("issue", { type: "number", demandOption: true, describe: "Issue number to address" })
  .option("token", { type: "string", demandOption: true, describe: "GitHub PAT" })
  .option("patch", { type: "string", demandOption: true, describe: "Path to .diff patch file" })
  .option("workdir", { type: "string", default: "./workdir", describe: "Temporary working directory" })
  .help()
  .argv as any;

/* ---------- Main Flow ---------- */
(async () => {
  const octokit = new Octokit({ auth: argv.token });
  const [owner, repo] = argv.repo.split("/");

  // 1️⃣ Validate issue
  const issue = await fetchIssue(octokit, owner, repo, argv.issue);
  if (!issue.isPatchRequest) {
    console.error("❌ Issue does not appear to be a patch request. Aborting.");
    process.exit(1);
  }

  // 2️⃣ Gather repo metadata
  const repoInfo = await fetchRepoInfo(octokit, owner, repo);
  await ensureWorkdir(argv.workdir);
  const git = simpleGit(argv.workdir);

  // 3️⃣ Clone (or fetch) repository
  await cloneOrUpdateRepo(git, repoInfo.cloneUrl, repoInfo.defaultBranch);

  // 4️⃣ Load contribution guidelines (if any)
  const contribRules = await loadContributionRules(git, repoInfo.contributionFile);

  // 5️⃣ Build deterministic submission plan
  const plan = buildSubmissionPlan({
    repoInfo,
    issue,
    contribRules,
    patchPath: argv.patch,
  });

  // 6️⃣ Apply patch
  await applyPatch(git, plan.branchName, argv.patch, plan.commitMessage);

  // 7️⃣ Run tests
  const testsPassed = runTests(argv.workdir);
  if (!testsPassed) {
    console.error("❌ Tests failed after applying patch. Aborting.");
    process.exit(1);
  }

  // 8️⃣ Submit (push or PR)
  if (repoInfo.hasPushAccess) {
    await pushBranch(git, plan.branchName);
    console.log(`✅ Direct push succeeded on branch ${plan.branchName}`);
  } else {
    const prUrl = await createPullRequest(octokit, {
      owner,
      repo,
      head: plan.branchName,
      base: repoInfo.defaultBranch,
      title: plan.commitMessage,
      body: `Fixes #${issue.number}\n\n${issue.title}`,
    });
    console.log(`✅ Pull request created: ${prUrl}`);
  }

  // 9️⃣ Clean up (optional)
  // await fs.promises.rm(argv.workdir, { recursive: true, force: true });
})().catch((e) => {
  console.error("❌ Unexpected error:", e);
  process.exit(1);
});

/* ---------- Helper Functions ---------- */

async function fetchIssue(
  octokit: Octokit,
  owner: string,
  repo: string,
  number: number
): Promise<IssueInfo> {
  const { data } = await octokit.issues.get({ owner, repo, issue_number: number });
  const isPatchRequest =
    data.labels.some((l) => (typeof l === "string" ? l.includes("patch") : l.name.includes("patch"))) ||
    /apply.*patch/i.test(data.title) ||
    /apply.*patch/i.test(data.body ?? "");

  return {
    number: data.number,
    title: data.title,
    body: data.body ?? "",
    labels: data.labels.map((l) => (typeof l === "string" ? l : l.name)),
    author: data.user?.login ?? "unknown",
    isPatchRequest,
  };
}

async function fetchRepoInfo(
  octokit: Octokit,
  owner: string,
  repo: string
): Promise<RepoInfo> {
  const { data } = await octokit.repos.get({ owner, repo });
  const permission = data.permissions?.push ?? false;
  const contribFile = await locateContributionFile(owner, repo, octokit);
  return {
    owner,
    name: repo,
    defaultBranch: data.default_branch,
    cloneUrl: data.clone_url,
    hasPushAccess: permission,
    contributionFile: contribFile,
  };
}

async function locateContributionFile(
  owner: string,
  repo: string,
  octokit: Octokit
): Promise<string | undefined> {
  const candidates = ["CONTRIBUTING.md", "docs/CONTRIBUTING.md"];
  for (const path of candidates) {
    try {
      await octokit.repos.getContent({ owner, repo, path });
      return path;
    } catch {
      // ignore
    }
  }
  return undefined;
}

async function ensureWorkdir(dir: string) {
  await fs.promises.mkdir(dir, { recursive: true });
}

async function cloneOrUpdateRepo(git: SimpleGit, url: string, branch: string) {
  if (fs.existsSync(path.join(git.cwd, ".git"))) {
    await git.fetch();
    await git.checkout(branch);
    await git.pull("origin", branch);
  } else {
    await git.clone(url, ".", ["--branch", branch, "--depth", "1"]);
  }
}

async function loadContributionRules(
  git: SimpleGit,
  contribPath?: string
): Promise<string | null> {
  if (!contribPath) return null;
  const fullPath = path.join(git.cwd, contribPath);
  try {
    return await fs.promises.readFile(fullPath, "utf8");
  } catch {
    return null;
  }
}

function buildSubmissionPlan(params: {
  repoInfo: RepoInfo;
  issue: IssueInfo;
  contribRules: string | null;
  patchPath: string;
}): SubmissionPlan {
  const branchName = `patch-${params.issue.number}-${Date.now()}`;
  const commitMessage = `Patch for #${params.issue.number}: ${params.issue.title}`;

  // Deterministic file list: parse the diff for affected files
  const diffContent = fs.readFileSync(params.patchPath, "utf8");
  const files = Array.from(diffContent.matchAll(/^diff --git a\/(.+?) b\/(.+)$/gm)).map(
    (m) => m[2]
  );

  // Determine test command from contribution rules (simple heuristic)
  let testCmd = "npm test";
  if (params.contribRules) {
    const match = params.contribRules.match(/npm\s+run\s+test|yarn\s+test/);
    if (match) testCmd = match[0];
  }

  return {
    filesToModify: files,
    testsToRun: [testCmd],
    branchName,
    commitMessage,
  };
}

async function applyPatch(
  git: SimpleGit,
  branch: string,
  patchPath: string,
  commitMessage: string
) {
  await git.checkoutLocalBranch(branch);
  // Apply patch using git apply
  execSync(`git apply "${patchPath}"`, { cwd: git.cwd, stdio: "inherit" });
  await git.add(".");
  await git.commit(commitMessage);
}

function runTests(workdir: string): boolean {
  try {
    execSync("npm install", { cwd: workdir, stdio: "ignore" });
    execSync("npm test", { cwd: workdir, stdio: "inherit" });
    return true;
  } catch {
    return false;
  }
}

async function pushBranch(git: SimpleGit, branch: string) {
  await git.push("origin", branch);
}

interface PRParams {
  owner: string;
  repo: string;
  head: string;
  base: string;
  title: string;
  body: string;
}
async function createPullRequest(octokit: Octokit, params: PRParams): Promise<string> {
  const { data } = await octokit.pulls.create({
    owner: params.owner,
    repo: params.repo,
    head: params.head,
    base: params.base,
    title: params.title,
    body: params.body,
  });
  return data.html_url;
}