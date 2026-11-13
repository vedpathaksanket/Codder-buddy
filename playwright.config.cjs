const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/browser',
  timeout: 30000,
  use: { baseURL: 'http://127.0.0.1:8765', screenshot: 'only-on-failure' },
  webServer: {
    command: 'uv run python -m tests.browser_server',
    url: 'http://127.0.0.1:8765/healthz',
    reuseExistingServer: false,
    timeout: 30000,
  },
});
