# Deploy Check

Use this before pushing the app to Render or another host:

```powershell
.\deploy-check.ps1
```

Or from npm:

```bash
npm run deploy:check
```

What it does:

1. Verifies the core deploy files are present.
2. Checks the local backend `.env` for the main secret/token hints and prints warnings if they are missing.
3. Runs the backend smoke suite.
4. Runs the Playwright browser suite when Node.js is available.

Optional:

```powershell
.\deploy-check.ps1 -Full
```

That also runs the retrain smoke path before the browser checks.
