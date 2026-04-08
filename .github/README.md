# GitHub Automation

This repository includes:

- `ci-deploy.yml` - runs the deploy check on pull requests and on pushes to `main`
- Render blueprint support via `render.yaml`
- A local deploy gate via `deploy-check.ps1`

## What still needs GitHub settings

1. Add the repository secret `RENDER_DEPLOY_HOOK_URL` if you want the workflow to trigger deployment automatically after tests pass.
2. Push the repository to GitHub and enable Actions.
3. Set the default branch to `main` if you want the deploy job to run automatically on pushes.

