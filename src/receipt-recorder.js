const crypto = require('crypto');
const fs = require('fs').promises;
const path = require('path');

class ReceiptRecorder {
  constructor(config) {
    this.config = config;
    this.receiptsDir = config.receiptsDir || path.join(__dirname, '../receipts');
  }

  async record(result) {
    const receipt = {
      id: this.generateId(),
      timestamp: new Date().toISOString(),
      type: result.type,
      data: result,
      hash: this.computeHash(result)
    };

    await this.ensureReceiptsDir();
    await this.saveReceipt(receipt);

    return receipt;
  }

  generateId() {
    return crypto.randomUUID();
  }

  computeHash(data) {
    const dataStr = JSON.stringify(data);
    return crypto.createHash('sha256').update(dataStr).digest('hex');
  }

  async ensureReceiptsDir() {
    try {
      await fs.mkdir(this.receiptsDir, { recursive: true });
    } catch (e) {
      // Directory may already exist
    }
  }

  async saveReceipt(receipt) {
    const filename = `${receipt.id}.json`;
    const filepath = path.join(this.receiptsDir, filename);
    await fs.writeFile(filepath, JSON.stringify(receipt, null, 2));
    return receipt;
  }

  async getReceipt(receiptId) {
    const filepath = path.join(this.receiptsDir, `${receiptId}.json`);
    try {
      const data = await fs.readFile(filepath, 'utf8');
      return JSON.parse(data);
    } catch (e) {
      return null;
  }

  async listReceipts(limit = 10) {
    await this.ensureReceiptsDir();
    const files = await fs.readdir(this.receiptsDir);
    
    return Promise.all(
      files.slice(-limit).map(async file => {
        const data = await fs.readFile(path.join(this.receiptsDir, file), 'utf8');
        return JSON.parse(data);
      })
    );
  }
}

module.exports = { ReceiptRecorder };
