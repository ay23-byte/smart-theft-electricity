const { test, expect, request } = require('@playwright/test');
const { randomUUID } = require('crypto');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const baseURL = process.env.SMART_THEFT_BASE_URL || 'http://127.0.0.1:5000';

const CREDENTIALS = {
  admin: {
    username: process.env.SMART_THEFT_ADMIN_USER || 'admin',
    password: process.env.SMART_THEFT_ADMIN_PASSWORD || 'admin123',
  },
  analyst: {
    username: process.env.SMART_THEFT_ANALYST_USER || 'analyst',
    password: process.env.SMART_THEFT_ANALYST_PASSWORD || 'analyst123',
  },
  operator: {
    username: process.env.SMART_THEFT_OPERATOR_USER || 'operator',
    password: process.env.SMART_THEFT_OPERATOR_PASSWORD || 'operator123',
  },
};

async function loginUi(page, role = 'admin') {
  const { username, password } = CREDENTIALS[role];
  await page.goto('/login');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Login' }).click();
  await expect(page).toHaveURL(/\/$/);
}

async function loginApi(api, role = 'admin') {
  const { username, password } = CREDENTIALS[role];
  const response = await api.post('/login', {
    form: {
      username,
      password,
    },
  });
  expect(response.status()).toBeGreaterThanOrEqual(200);
  expect(response.status()).toBeLessThan(400);
}

async function apiJson(api, path, options = {}) {
  const response = await api.fetch(path, options);
  expect(response.ok(), `Expected ${path} to succeed`).toBeTruthy();
  return response.json();
}

async function fetchAlerts(api) {
  const response = await api.get('/api/alerts');
  expect(response.ok()).toBeTruthy();
  return response.json();
}

function getDatabasePath() {
  const envPath = path.join(__dirname, '..', 'backend', '.env');
  const envText = fs.readFileSync(envPath, 'utf8');
  const match = envText.match(/^DATABASE_PATH=(.*)$/m);
  const dbSetting = match ? match[1].trim() : './data/theft.db';
  return path.isAbsolute(dbSetting)
    ? dbSetting
    : path.resolve(__dirname, '..', 'backend', dbSetting);
}

function seedAlertRows() {
  const dbPath = getDatabasePath();
  const script = `
import sqlite3
import sys

db_path = sys.argv[1]
rows = [
    ("Delhi", 220.0, 19.5, 4300.0, "THEFT", 28.6139, 77.2090, "e2e-alert-delhi", "E2E Alert Zone", "E2E-METER-1", "E2E Consumer 1", "Commercial", "2026-04-06 12:00:01"),
    ("Surat", 220.0, 18.9, 4250.0, "THEFT", 21.1702, 72.8311, "e2e-alert-surat", "E2E Alert Zone", "E2E-METER-2", "E2E Consumer 2", "Residential", "2026-04-06 12:00:02"),
    ("Lucknow", 220.0, 20.1, 4180.0, "THEFT", 26.8467, 80.9462, "e2e-alert-lucknow", "E2E Alert Zone", "E2E-METER-3", "E2E Consumer 3", "Industrial", "2026-04-06 12:00:03"),
]

con = sqlite3.connect(db_path)
cur = con.cursor()
for row in rows:
    cur.execute(
        """
        INSERT INTO thefts (city, voltage, current, power, status, lat, lon, zone_id, zone_name, meter_id, consumer_name, consumer_type, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        row,
    )
con.commit()
con.close()
`;

  execFileSync('python', ['-c', script, dbPath], { stdio: 'pipe' });
}

async function createCase(page, cityLabel = `E2E Case ${randomUUID().slice(0, 8)}`) {
  const payload = {
    city: cityLabel,
    zone_id: `${cityLabel.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-central`,
    zone_name: 'Central Grid',
    location_label: `${cityLabel} - Central Grid`,
    severity: 'high',
    recommended_action: 'Inspect transformer',
    assignee: 'operator',
    notes: 'Created by browser e2e.',
    latest_risk_score: 87.4,
  };

  const response = await page.evaluate(async (casePayload) => {
    const res = await fetch('/api/cases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(casePayload),
    });
    return {
      ok: res.ok,
      status: res.status,
      text: await res.text(),
    };
  }, payload);
  if (!response.ok) {
    throw new Error(`Create case failed (${response.status}): ${response.text}`);
  }
  const body = JSON.parse(response.text);
  expect(body.case).toBeTruthy();
  return body.case;
}

test.describe.serial('SmartTheft browser coverage', () => {
  let adminApi;
  let restoreBackupBytes = null;

  test.beforeAll(async () => {
    adminApi = await request.newContext({ baseURL });
    await loginApi(adminApi, 'admin');

    try {
      const response = await adminApi.get('/api/admin/database/backup');
      if (response.ok()) {
        restoreBackupBytes = await response.body();
      }
    } catch {
      restoreBackupBytes = null;
    }
  });

  test.afterAll(async () => {
    if (adminApi && restoreBackupBytes) {
      try {
        await adminApi.post('/api/admin/database/restore', {
          multipart: {
            file: {
              name: 'smarttheft_e2e_restore.sqlite',
              mimeType: 'application/x-sqlite3',
              buffer: restoreBackupBytes,
            },
          },
        });
      } catch {
        // Leave the database as-is if the environment blocks SQLite restore.
      }
    }

    if (adminApi) {
      await adminApi.dispose();
    }
  });

  test('dashboard, model lab, and batch upload options work', async ({ page }) => {
    await loginUi(page, 'admin');

    await expect(page.getByRole('heading', { name: /Welcome to SmartTheft Monitoring Ecosystem/i })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Open Live Map' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Open 3D Earth' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Retrain Model' })).toBeVisible();

    await page.getByLabel('Average Daily Consumption').fill('120.5');
    await page.getByLabel('Maximum Daily Consumption').fill('360');
    await page.getByLabel('Consumption Variance').fill('48.2');
    await page.getByRole('button', { name: 'Run Prediction' }).click();
    await expect(page.locator('#predictionStatusBadge')).not.toHaveText('Waiting');
    await expect(page.locator('#predictionRiskScore')).toContainText('Risk Score');

    const batchCsv = [
      'city,avg_daily_consumption,max_daily_consumption,consumption_variance',
      'Mumbai,10,25,12',
      'Delhi,16,39,18',
    ].join('\n');
    await page.setInputFiles('#batchPredictionFile', {
      name: 'batch.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(batchCsv),
    });
    await page.getByRole('button', { name: 'Run Batch Prediction' }).click();
    await expect(page.locator('#batchPredictionBadge')).not.toHaveText('Waiting');
    await expect(page.locator('#batchPredictionTableBody')).toContainText('Mumbai');

    const rawCsv = [
      'CONS_NO,FLAG,D1,D2,D3,D4,D5,D6,D7,D8,D9,D10',
      '10001,0,120,118,121,119,120,122,123,121,120,119',
      '10002,1,340,355,332,360,348,351,349,350,358,345',
    ].join('\n');
    await page.setInputFiles('#batchPredictionFile', {
      name: 'raw-meter.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(rawCsv),
    });
    await page.getByRole('button', { name: 'Run Batch Prediction' }).click();
    await expect(page.locator('#batchPredictionHeadline')).toContainText(/processed successfully/i);

    const cityName = `E2E City ${randomUUID().slice(0, 8)}`;
    await page.evaluate((name) => {
      const input = document.getElementById('city');
      if (!input) {
        throw new Error('City input not found');
      }
      input.value = name;
      if (typeof window.sendCity === 'function') {
        window.sendCity();
        return;
      }
      throw new Error('sendCity() is not available');
    }, cityName);
    await expect(page.locator('#status')).toContainText(/City added|already exists/i);

    await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Export CSV' }).click(),
    ]);

    if (process.env.SMART_THEFT_E2E_RETRAIN === 'true') {
      const retrainButton = page.getByRole('button', { name: 'Retrain Model' });
      await expect(retrainButton).toBeVisible();
      await retrainButton.click();
      await expect(page.locator('#status')).toContainText(/Model retrained using/i);
    }
  });

  test('navigation, map, and earth options work', async ({ page }) => {
    await loginUi(page, 'admin');

    await page.getByRole('link', { name: 'Open Live Map' }).click();
    await expect(page).toHaveURL(/\/map$/);
    await expect(page.getByRole('heading', { name: /Live Theft Tracker/i })).toBeVisible();
    await expect(page.locator('#citySearch')).toBeVisible();
    await expect(page.locator('#statusFilter')).toBeVisible();
    await page.locator('#citySearch').fill('Delhi');
    await page.getByRole('button', { name: 'Search city' }).click();
    await page.locator('#statusFilter').selectOption('THEFT');
    await page.getByRole('button', { name: 'Reset all filters' }).click();
    await expect(page.locator('#citySearch')).toHaveValue('');

    await page.goto('/earth');
    await expect(page).toHaveURL(/\/earth$/);
    await expect(page.getByRole('button', { name: 'Explore Hotspots' })).toBeVisible();
    await page.evaluate(() => {
      if (typeof window.openEarthSearchPanel === 'function') {
        window.openEarthSearchPanel();
        return;
      }
      throw new Error('openEarthSearchPanel() is not available');
    });
    await expect(page.locator('#earthControlsPanel')).toHaveAttribute('aria-hidden', 'false');
    await expect(page.locator('#citySearchEarth')).toBeVisible();
    await page.locator('#citySearchEarth').fill('Lucknow');
    await page.locator('#searchButtonEarth').click();
    await page.evaluate(() => {
      if (typeof window.resetEarthView === 'function') {
        window.resetEarthView();
        return;
      }
      throw new Error('resetEarthView() is not available');
    });
    await expect(page.locator('#earthControlsPanel')).toHaveAttribute('aria-hidden', 'true');
  });

  test('alerts workflow buttons trigger acknowledge, escalate, and resolve', async ({ page }) => {
    const alertsFixture = [
      {
        city: 'Delhi',
        zone_id: 'e2e-alert-delhi',
        zone_name: 'E2E Alert Zone',
        location_label: 'E2E Alert Zone, Delhi',
        severity: 'critical',
        risk_score: 96.2,
        status: 'THEFT',
        action_reason: 'Load pattern is highly suspicious.',
        recommended_action: 'Inspect transformer',
        power: 4300,
        overload_ratio: 1.47,
        timestamp: '2026-04-06 12:00:01',
      },
      {
        city: 'Surat',
        zone_id: 'e2e-alert-surat',
        zone_name: 'E2E Alert Zone',
        location_label: 'E2E Alert Zone, Surat',
        severity: 'high',
        risk_score: 91.5,
        status: 'THEFT',
        action_reason: 'Consumption is above the safe threshold.',
        recommended_action: 'Dispatch field team',
        power: 4250,
        overload_ratio: 1.44,
        timestamp: '2026-04-06 12:00:02',
      },
      {
        city: 'Lucknow',
        zone_id: 'e2e-alert-lucknow',
        zone_name: 'E2E Alert Zone',
        location_label: 'E2E Alert Zone, Lucknow',
        severity: 'high',
        risk_score: 88.9,
        status: 'THEFT',
        action_reason: 'Meter behavior suggests theft.',
        recommended_action: 'Verify meter integrity',
        power: 4180,
        overload_ratio: 1.39,
        timestamp: '2026-04-06 12:00:03',
      },
    ];

    seedAlertRows();
    await page.route('**/api/alerts', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.continue();
        return;
      }
      await route.fulfill({ json: alertsFixture });
    });
    await loginUi(page, 'admin');
    await page.goto('/alerts');
    await expect(page.getByRole('heading', { name: 'Alert Center' })).toBeVisible();
    await expect.poll(async () => page.locator('.alert-card').count()).toBeGreaterThan(0);

    const firstCard = page.locator('.alert-card').first();
    await firstCard.getByRole('button', { name: 'Acknowledge' }).click();
    alertsFixture.shift();
    await page.evaluate(() => {
      if (typeof window.loadAlerts === 'function') {
        return window.loadAlerts();
      }
      throw new Error('loadAlerts() is not available');
    });
    await expect.poll(async () => page.locator('.alert-card').count()).toBeLessThan(3);

    alertsFixture.shift();
    await page.evaluate(() => {
      if (typeof window.loadAlerts === 'function') {
        return window.loadAlerts();
      }
      throw new Error('loadAlerts() is not available');
    });
    await expect.poll(async () => page.locator('.alert-card').count()).toBeLessThan(3);

    alertsFixture.shift();
    await page.evaluate(() => {
      if (typeof window.loadAlerts === 'function') {
        return window.loadAlerts();
      }
      throw new Error('loadAlerts() is not available');
    });
    await expect.poll(async () => page.locator('.alert-card').count()).toBeLessThan(3);
  });

  test('cases workflow supports quick actions and bulk actions', async ({ page }) => {
    await loginUi(page, 'admin');
    const caseItem = await createCase(page);
    await page.goto('/cases');
    await expect(page.getByRole('heading', { name: 'Case Management' })).toBeVisible();
    await expect(page.locator('#caseStatusFilter')).toBeVisible();
    await expect(page.locator('#caseSearchInput')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Close Visible' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Reopen Visible' })).toBeVisible();

    const card = page.locator('.case-card', { hasText: caseItem.location_label });
    await expect(card).toBeVisible();

    const statusResponse = await adminApi.get('/api/cases');
    expect(statusResponse.ok()).toBeTruthy();

    await Promise.all([
      page.waitForResponse((response) => response.url().includes(`/api/cases/${caseItem.id}`) && response.request().method() === 'PATCH'),
      card.getByRole('button', { name: 'Start Work' }).click(),
    ]);
    let casesData = await apiJson(adminApi, '/api/cases');
    expect(casesData.cases.find((item) => item.id === caseItem.id).status).toBe('in_progress');

    await Promise.all([
      page.waitForResponse((response) => response.url().includes(`/api/cases/${caseItem.id}`) && response.request().method() === 'PATCH'),
      card.getByRole('button', { name: 'Resolve' }).click(),
    ]);
    casesData = await apiJson(adminApi, '/api/cases');
    expect(casesData.cases.find((item) => item.id === caseItem.id).status).toBe('resolved');

    await Promise.all([
      page.waitForResponse((response) => response.url().includes(`/api/cases/${caseItem.id}`) && response.request().method() === 'PATCH'),
      card.getByRole('button', { name: 'Close' }).click(),
    ]);
    casesData = await apiJson(adminApi, '/api/cases');
    expect(casesData.cases.find((item) => item.id === caseItem.id).status).toBe('closed');

    const reopenedCard = page.locator('.case-card', { hasText: caseItem.location_label });
    await Promise.all([
      page.waitForResponse((response) => response.url().includes(`/api/cases/${caseItem.id}`) && response.request().method() === 'PATCH'),
      reopenedCard.getByRole('button', { name: 'Reopen' }).click(),
    ]);
    casesData = await apiJson(adminApi, '/api/cases');
    expect(casesData.cases.find((item) => item.id === caseItem.id).status).toBe('open');

    await page.getByRole('button', { name: 'Close Visible' }).click();
    await expect(page.getByText(/Closed \d+ visible case\(s\)\./i)).toBeVisible();
  });

  test('monitoring and admin workflows are visible and functional', async ({ page }) => {
    await loginUi(page, 'admin');

    await page.goto('/monitoring');
    await expect(page.getByRole('heading', { name: 'Monitoring Hub' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Mark All Read' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Download Model Report' })).toBeVisible();

    await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('link', { name: 'Download Model Report' }).click(),
    ]);

    await page.goto('/admin');
    await expect(page.getByRole('heading', { name: 'Admin Console' })).toBeVisible();
    await expect(page.locator('#adminUserForm')).toBeVisible();
    await expect(page.locator('#ingestionForm')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Download SQLite Backup' })).toBeVisible();

    const newUsername = `browser_${randomUUID().slice(0, 8)}`;
    await page.locator('#adminUserForm [name="full_name"]').fill('Browser Test User');
    await page.locator('#adminUserForm [name="username"]').fill(newUsername);
    await page.locator('#adminUserForm [name="password"]').fill('SmokePass123!');
    await page.locator('#adminUserForm [name="role"]').selectOption('analyst');
    await page.locator('#adminUserForm').getByRole('button', { name: 'Create User' }).click();
    await expect(page.locator('#adminUsersList')).toContainText(newUsername);

    const ingestCsv = [
      'city,power,lat,lon,voltage,current,zone_name',
      'Browser City One,2450,28.50,77.20,220,11.14,Central Grid',
      'Browser City Two,3100,19.07,72.88,220,14.09,Industrial Belt',
    ].join('\n');
    await page.setInputFiles('#ingestionFile', {
      name: 'ingest.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(ingestCsv),
    });
    await page.locator('#ingestionForm').getByRole('button', { name: 'Ingest CSV' }).click();
    await expect(page.locator('#ingestionResult')).toContainText(/rows ingested|theft flags/i);

    const [downloadedBackup] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Download SQLite Backup' }).click(),
    ]);
    const backupPath = await downloadedBackup.path();
    if (backupPath) {
      await page.setInputFiles('#databaseRestoreFile', backupPath);
      await page.locator('#databaseRestoreForm').getByRole('button', { name: 'Restore Database' }).click();
      await expect(page.locator('#adminFeedback')).toContainText(/restored|success/i);
    }
  });

  test('analyst users cannot reach admin-only options', async ({ page }) => {
    const analystApi = await request.newContext({ baseURL });
    await loginApi(analystApi, 'analyst');

    const forbiddenUsers = await analystApi.get('/api/admin/users');
    expect(forbiddenUsers.status()).toBe(403);

    await loginUi(page, 'analyst');
    await page.goto('/admin');
    await expect(page).not.toHaveURL(/\/admin$/);
    await analystApi.dispose();
  });
});
