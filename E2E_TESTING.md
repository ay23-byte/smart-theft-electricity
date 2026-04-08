# SmartTheft Browser Testing

This project now includes a Playwright smoke suite that covers the main user journeys:

- Dashboard
- Map
- 3D Earth
- Alerts
- Cases
- Monitoring
- Admin
- Prediction form
- Batch upload
- Add city
- CSV ingestion
- User management
- Backup and restore

## Run

1. Install browser test dependencies:

```bash
npm install
npx playwright install
```

2. Start the Flask app:

```bash
cd backend
python app.py
```

3. Run the browser suite:

```bash
npm run test:e2e
```

Or run the full project smoke path from the repo root:

```powershell
.\run-all-tests.ps1
```

For a preflight + full verification pass before deployment, use:

```powershell
.\deploy-check.ps1
```

If Node.js is not installed, the launcher will finish the backend smoke run and skip the browser suite with a warning.

## Optional

- `npm run test:e2e:headed` to watch the browser while it runs.
- `npm run test:e2e:debug` to step through failures.
- `npm run deploy:check` to run the deploy preflight and the full smoke suite.
- Set `SMART_THEFT_E2E_RETRAIN=true` to include the dashboard model retrain button in the browser run.
- `.\run-all-tests.ps1 -Full` runs the backend smoke test with retraining and then the browser suite with retraining enabled.

## Base URL

Set `SMART_THEFT_BASE_URL` if your app is not running on `http://127.0.0.1:5000`.

## Notes

- The suite restores the database at the end when a backup is available.
- It is serial by design, because several workflows mutate the same backing data.
