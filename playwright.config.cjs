const { defineConfig } = require('@playwright/test');
const os = require('os');
const path = require('path');

const baseURL = process.env.SMART_THEFT_BASE_URL || 'http://127.0.0.1:5000';
const outputDir = process.env.PLAYWRIGHT_OUTPUT_DIR || path.join(os.tmpdir(), 'smarttheft-playwright');

module.exports = defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  outputDir,
  expect: {
    timeout: 15_000,
  },
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
});
