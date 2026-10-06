const { PatchSubmissionEngine } = require('./patch-submission-engine');
const { ReceiptRecorder } = require('./receipt-recorder');
const { CIMonitor } = require('./ci-monitor');
const { CapabilityManager } = require('./capability-manager');

class LouisOS {
  constructor(config) {
    this.config = config;
    this.patchEngine = new PatchSubmissionEngine(config);
    this.receiptRecorder = new ReceiptRecorder(config);
    this.ciMonitor = new CIMonitor(config);
    this.capabilityManager = new CapabilityManager(config);
  }

  async processIssue(issueId) {
    console.log(`Processing issue #${issueId}`);
    
    // Step 1: Inspect repository metadata
    const repoInfo = await this.patchEngine.inspectRepository();
    console.log('Repository info:', repoInfo);

    // Step 2: Build submission plan
    const plan = await this.patchEngine.buildSubmissionPlan(issueId);
    console.log('Submission plan:', plan);

    // Step 3: Execute patch
    const result = await this.patchEngine.executePatch(plan);
    console.log('Patch result:', result);

    // Step 4: Record receipt
    const receipt = await this.receiptRecorder.record(result);
    console.log('Receipt recorded:', receipt);

    // Step 5: Monitor CI
    const ciStatus = await this.ciMonitor.monitor(result.prUrl);
    console.log('CI Status:', ciStatus);

    return { receipt, ciStatus };
  }

  async start() {
    console.log('Louis OS starting...');
    
    // Check for pending issues
    const pendingIssues = await this.patchEngine.listPendingIssues();
    
    for (const issue of pendingIssues) {
      await this.processIssue(issue.id);
    }

    // Start CI monitoring
    this.ciMonitor.start();
  }
}

module.exports = { LouisOS };
