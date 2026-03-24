# Scalingo Deployment Guide

This guide is the production path for the Telegram survey bot.

## Recommended Production Topology
- App hosting: Scalingo
- Process type: `worker`
- Database: Scalingo PostgreSQL addon
- Google reporting: Google Sheets
- Runtime mode: polling

No domain is required for this version because the bot uses polling, not webhook.

## Before You Start
You need:
1. A Scalingo account
2. A Git repository with this project
3. A Telegram bot token from BotFather
4. A Google Sheet already shared with your service account
5. Your Google service account JSON content or JSON file

## Important Architecture Rule
- PostgreSQL is the source of truth
- Google Sheets is reporting only
- CSV is import-only

## Phase 5 Checklist
Before deploy, confirm:
1. `Procfile` contains:
   - `worker: python -m app.main`
2. `requirements.txt` is clean
3. `.env.example` contains no real secrets
4. The app can build schema on startup
5. CSV import works locally

## Step 1. Push the Project to Git
If the project is not yet in Git:

```powershell
git init
git add .
git commit -m "Prepare project for Scalingo deploy"
```

If you already have a remote:

```powershell
git add .
git commit -m "Phase 5 deployment preparation"
git push
```

## Step 2. Create the Scalingo App
1. Open the Scalingo dashboard
2. Click `Create an app`
3. Choose your app name
4. Connect your Git provider or prepare for git push deploy

## Step 3. Add PostgreSQL
In Scalingo:
1. Open the app
2. Go to `Resources`
3. Click `Add an addon`
4. Choose PostgreSQL
5. Select a plan

Scalingo automatically adds:
- `SCALINGO_POSTGRESQL_URL`
- `DATABASE_URL`

Scalingo documents that `DATABASE_URL` is an alias for the PostgreSQL connection URI.  
Source: https://doc.scalingo.com/databases/postgresql/getting-started/connecting

## Step 4. Configure Environment Variables
In the app dashboard, open `Environment` and add:

- `BOT_TOKEN`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`

Do not set `GOOGLE_SERVICE_ACCOUNT_FILE` on Scalingo unless you intentionally manage a file in the container.

Example:

```text
BOT_TOKEN=your_real_bot_token
GOOGLE_SHEET_ID=your_google_sheet_id
GOOGLE_SERVICE_ACCOUNT_JSON={...full json...}
```

Do not paste secrets into source code.

## Step 5. Deploy
If using GitHub integration:
1. Connect the repository
2. Trigger deploy from the dashboard

If using git remote deploy:
1. Add the Scalingo git remote
2. Push the branch

After deploy, verify build success in logs.

## Step 6. Scale the Correct Process
For this bot:
- `worker = 1`
- `web = 0`

Only one polling worker should run.

If you run more than one worker with the same bot token, Telegram will return conflict errors.

## Step 7. Initialize / Verify Database
The application now bootstraps schema on startup, so first boot creates missing tables automatically.

Still, for safety, after first deploy:
1. Open the app logs
2. Confirm the worker starts cleanly
3. Confirm there are no SQLAlchemy schema errors

## Step 8. Import Drivers into Production
After the app and database exist, run the import using a one-off command on Scalingo.

Recommended approach:
1. Upload or commit the current `DRIVERS_IMPORT.csv`
2. Run:

```powershell
python -m scripts.import_drivers --file DRIVERS_IMPORT.csv
```

On Scalingo this should be executed as a one-off command from the platform console or CLI.

## Step 9. Verify Google Sheets
Make sure the Google Sheet contains:
- `Survey_Wide`
- `Drivers_Status`

If they do not exist, the app creates them automatically.

After one completed survey, verify:
1. `Survey_Wide` gets a new row
2. `Drivers_Status` updates the matching driver row

## Step 10. Production Smoke Test
Test these scenarios:
1. Driver with no dispatcher assignments
2. Driver with 1 dispatcher
3. Driver with 2 dispatchers
4. Driver with 3 dispatchers
5. Existing driver re-running in the same quarter
6. Google Sheets export after completion

## Operational Notes
1. Keep worker count at 1
2. Do not use SQLite in production
3. Use Scalingo PostgreSQL as the production DB
4. Keep Google credentials in environment variables only
5. Keep CSV only as import input

## Useful Scalingo References
- PostgreSQL connection env vars: https://doc.scalingo.com/databases/postgresql/getting-started/connecting
- PostgreSQL addon provisioning: https://doc.scalingo.com/databases/postgresql/getting-started
- Remote DB access: https://doc.scalingo.com/databases/postgresql/getting-started/accessing

## Recommended Go-Live Order
1. Deploy app
2. Add PostgreSQL
3. Add env vars
4. Scale worker to 1
5. Import drivers
6. Complete one live test survey
7. Verify Google Sheets
8. Start production usage
