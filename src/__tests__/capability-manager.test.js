const { CapabilityManager } = require('../capability-manager');
const fs = require('fs').promises;

jest.mock('fs');

describe('CapabilityManager', () => {
  let manager;
  const mockConfig = {
    capabilitiesFile: '/tmp/capabilities.json',
    githubToken: 'mock-token'
  };

  beforeEach(() => {
    manager = new CapabilityManager(mockConfig);
  });

  afterEach(async () => {
    await fs.rm('/tmp', { recursive: true, force: true }).catch(() => {});
  });

  describe('detectMissingCapabilities', () => {
    it('should detect missing github access', async () => {
      const noTokenManager = new CapabilityManager({ 
        ...mockConfig, 
        githubToken: null 
      });
      
      const issue = { body: 'Fix bug', labels: [] };
      const missing = await noTokenManager.detectMissingCapabilities(issue);
      
      expect(missing).toContainEqual(expect.objectContaining({ name: 'github-access' }));
    });

    it('should not report github access if token exists', async () => {
      const issue = { body: 'Fix bug', labels: [] };
      const missing = await manager.detectMissingCapabilities(issue);
      
      expect(missing).not.toContainEqual(expect.objectContaining({ name: 'github-access' }));
    });
  });

  describe('persistMissingCapability', () => {
    it('should save missing capability', async () => {
      await manager.persistMissingCapability({ name: 'test-cap', details: 'test' });
      
      const data = await fs.readFile(mockConfig.capabilitiesFile, 'utf8');
      const capabilities = JSON.parse(data);
      
      expect(capabilities.missing).toContainEqual(expect.objectContaining({ name: 'test-cap' }));
    });
  });
});
