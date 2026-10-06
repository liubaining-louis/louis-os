const fs = require('fs').promises;
const path = require('path');

class CapabilityManager {
  constructor(config) {
    this.config = config;
    this.capabilitiesFile = config.capabilitiesFile || path.join(__dirname, '../capabilities.json');
  }

  async loadCapabilities() {
    try {
      const data = await fs.readFile(this.capabilitiesFile, 'utf8');
      return JSON.parse(data);
    } catch (e) {
      return { capabilities: [], missing: [] };
    }
  }

  async saveCapabilities(capabilities) {
    await fs.writeFile(this.capabilitiesFile, JSON.stringify(capabilities, null, 2));
  }

  async detectMissingCapabilities(issue) {
    const current = await this.loadCapabilities();
    const required = this.extractRequiredCapabilities(issue);
    
    const missing = required.filter(r => 
      !current.capabilities.some(c => c.name === r.name && c.valid)
    );

    return missing;
  }

  extractRequiredCapabilities(issue) {
    const capabilities = [];
    
    // Check for common capability requirements
    if (issue.labels?.some(l => l.name === 'payout')) {
      capabilities.push({ name: 'payment-verification', valid: false });
    }
    
    if (issue.body?.includes('KYC')) {
      capabilities.push({ name: 'identity-verification', valid: false });
    }

    // GitHub API access is always required
    capabilities.push({ name: 'github-access', valid: !!this.config.githubToken });

    return capabilities;
  }

  async persistMissingCapability(capability) {
    const current = await this.loadCapabilities();
    
    // Add or update capability
    const existing = current.missing.find(m => m.name === capability.name);
    if (existing) {
      existing.details = capability.details;
      existing.persistedAt = new Date().toISOString();
    } else {
      current.missing.push({
        ...capability,
        persistedAt: new Date().toISOString()
      });
    }

    await this.saveCapabilities(current);
  }

  async markCapabilityAcquired(capabilityName) {
    const current = await this.loadCapabilities();
    
    // Move from missing to capabilities
    const missingIndex = current.missing.findIndex(m => m.name === capabilityName);
    if (missingIndex >= 0) {
      const [capability] = current.missing.splice(missingIndex, 1);
      capability.acquiredAt = new Date().toISOString();
      current.capabilities.push(capability);
    }

    await this.saveCapabilities(current);
  }

  async getPivotOpportunity(currentIssue) {
    const missing = await this.detectMissingCapabilities(currentIssue);
    
    if (missing.length === 0) {
      return null;
    }

    // Find alternative issues that don't require missing capabilities
    const alternatives = await this.findAlternativeIssues(missing);
    
    return alternatives.length > 0 ? alternatives[0] : null;
  }

  async findAlternativeIssues(missingCapabilities) {
    // Placeholder - would query GitHub API for issues without these requirements
    return [];
  }
}

module.exports = { CapabilityManager };
