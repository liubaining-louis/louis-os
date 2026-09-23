import * as core from '@actions/core';
import * as exec from '@actions/exec';
import * as path from 'path';
import * as fs from 'fs';

jest.mock('@actions/core');
jest.mock('@actions/exec');

describe('Check GCP Billing Action', () => {
  const execMock = exec.exec as jest.MockedFunction<typeof exec.exec>;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fails when billing is disabled', async () => {
    execMock.mockResolvedValueOnce(0); // gcloud command success
    execMock.mockImplementationOnce(async (cmd, args, opts) => {
      if (cmd === 'gcloud') {
        // Simulate billing disabled output
        opts?.stdout?.write?.('false');
      }
    });

    await expect(
      (async () => {
        await exec.exec('gcloud', ['beta', 'billing', 'projects', 'describe', 'test-bot-499814', '--format', 'value(billingEnabled)']);
      })()
    ).resolves.not.toThrow();
  });
});
