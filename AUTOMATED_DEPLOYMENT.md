# Automated Deployment

This project now includes a GitHub Actions pipeline that:

1. Installs backend and browser test dependencies.
2. Runs the deploy preflight checks.
3. Runs the full browser smoke suite on `main`.
4. Triggers a deployment webhook after tests pass, if configured.

It also includes a Render blueprint so the app can be created with the same runtime, disk, and env settings every time.

## What You Need To Set Up

Add this GitHub secret in your repository settings:

- `RENDER_DEPLOY_HOOK_URL`

Use the deployment hook URL from your host. The workflow will POST to that URL after the tests pass on `main`.

If you deploy on Render, you can also import the repo directly using [`render.yaml`](render.yaml). That blueprint sets:

- the Python web service
- the `gunicorn` start command
- a persistent disk for SQLite
- placeholder environment variables for secrets

## How It Works

- Pull requests run the deploy checks only.
- Pushes to `main` run the deploy checks and then call the deployment webhook.
- If the secret is missing, the deploy step is skipped safely.

## Local Manual Check

You can still validate everything locally with:

```powershell
.\deploy-check.ps1
```

Or:

```powershell
.\deploy-check.ps1 -Full
```

## Recommended Production Setup

- Keep `backend/.env` out of git.
- Set a real `SECRET_KEY`.
- Set `CESIUM_ION_TOKEN` if you use the globe view.
- Use a persistent SQLite volume or migrate to Postgres for production.
- Do not commit or deploy your local Python virtual environment (`venv/`, `.venv/`, `ENV/`). Render and GitHub Actions create their own isolated environments from `backend/requirements.txt`.
