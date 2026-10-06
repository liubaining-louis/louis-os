const { ReceiptRecorder } = require('../receipt-recorder');
const fs = require('fs').promises;

jest.mock('fs');

describe('ReceiptRecorder', () => {
  let recorder;
  const mockConfig = {
    receiptsDir: '/tmp/receipts'
  };

  beforeEach(() => {
    recorder = new ReceiptRecorder(mockConfig);
    fs.mkdir.mockResolvedValue(undefined);
    fs.writeFile.mockResolvedValue(undefined);
    fs.readFile.mockResolvedValue(null);
    fs.readdir.mockResolvedValue([]);
  });

  afterEach(async () => {
    await fs.rm(mockConfig.receiptsDir, { recursive: true, force: true }).catch(() => {});
  });

  describe('record', () => {
    it('should create a receipt with hash', async () => {
      const result = await recorder.record({ type: 'test', data: { foo: 'bar' } });
      
      expect(result).toHaveProperty('id');
      expect(result).toHaveProperty('timestamp');
      expect(result).toHaveProperty('hash');
      expect(result).toHaveProperty('type', 'test');
      expect(result).toHaveProperty('data');
    });

    it('should save receipt to file', async () => {
      await recorder.record({ type: 'test' });
      
      expect(fs.writeFile).toHaveBeenCalled();
    });
  });

  describe('getReceipt', () => {
    it('should return null for non-existent receipt', async () => {
      const receipt = await recorder.getReceipt('non-existent');
      expect(receipt).toBeNull();
    });

    it('should return receipt for existing file', async () => {
      const mockReceipt = { id: 'test-id', data: { foo: 'bar' } };
      fs.readFile.mockResolvedValue(JSON.stringify(mockReceipt));
      
      const receipt = await recorder.getReceipt('test-id');
      expect(receipt).toEqual(mockReceipt);
    });
  });
});
