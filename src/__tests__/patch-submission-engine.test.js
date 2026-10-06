const { PatchSubmissionEngine } = require('../patch-submission-engine');

describe('PatchSubmissionEngine', () => {
  let engine;
  const mockConfig = {
    githubToken: 'mock-token',
    owner: 'test-owner',
    repo: 'test-repo',
    githubUser: 'test-user',
    defaultBranch: 'main'
  };

  beforeEach(() => {
    engine = new PatchSubmissionEngine(mockConfig);
  });

  describe('isValidTargetIssue', () => {
    it('should reject pull requests', () => {
      const issue = { pull_request: {}, state: 'open', labels: [] };
      expect(engine.isValidTargetIssue(issue)).toBe(false);
    });

    it('should accept issues with valid labels', () => {
      const issue = { 
        pull_request: null, 
        state: 'open', 
        labels: [{ name: 'bug' }] 
      };
      expect(engine.isValidTargetIssue(issue)).toBe(true);
    });

    it('should accept open issues without labels', () => {
      const issue = { 
        pull_request: null, 
        state: 'open', 
        labels: [] 
      };
      expect(engine.isValidTargetIssue(issue)).toBe(true);
    });
  });

  describe('extractRequiredFiles', () => {
    it('should parse files from issue body', () => {
      const issue = {
        body: '**Files:** src/index.js, tests/test.js'
      };
      const files = engine.extractRequiredFiles(issue);
      expect(files).toContain('src/index.js');
      expect(files).toContain('tests/test.js');
    });

    it('should return empty array for missing files section', () => {
      const issue = { body: 'Some issue description' };
      const files = engine.extractRequiredFiles(issue);
      expect(files).toEqual([]);
    });
  });

  describe('extractTestCommand', () => {
    it('should parse custom test command', () => {
      const issue = { body: 'test: npm run test:custom' };
      expect(engine.extractTestCommand(issue)).toBe('npm');
    });

    it('should default to npm test', () => {
      const issue = { body: 'Fix a bug' };
      expect(engine.extractTestCommand(issue)).toBe('npm test');
    });
  });
});
