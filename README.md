# Quarterly Driver Survey Bot

Telegram bot for quarterly driver surveys with multilingual flow (EN/UZ/RU), per-department branching, SQL storage, dispatcher-specific ratings, and Google Sheets export.

## Features
- Language selection: English, Uzbek, Russian
- Driver identification by `unit`: for single-driver units bot asks "Is this you?", for team units bot shows all names for selection
- Quarterly survey flow with button-first UX
- Dispatcher assignments per driver, with separate dispatcher rating questions
- SQL database as source of truth
- CSV import for driver list and dispatcher assignments
- Google Sheets export for management reporting

## Departments
- HR
- Safety
- HOS / ELD
- Claims
- Fleet
- Dispatch
- Accounting
- Management

## Tech Stack
- Python 3.11+
- aiogram 3
- SQLAlchemy (async)
- PostgreSQL (recommended for production; SQLite works for local dev)
- gspread + Google service account

## Local Setup
1. Create bot in BotFather and get token.
2. Create `.env` based on `.env.example`.
3. Install dependencies:
```bash
pip install -r requirements.txt
```
4. Initialize database:
```bash
python -m scripts.init_db
```
5. (Optional) Import drivers from CSV:
```bash
python -m scripts.import_drivers --file drivers.csv
```
6. If you are upgrading from old schema, run:
```bash
python -m scripts.migrate_drivers_schema
```
7. Run feedback schema migration:
```bash
python -m scripts.migrate_feedback_schema
```
8. Run survey scope migration:
```bash
python -m scripts.migrate_survey_runs_driver_scope
```
9. Run bot:
```bash
python -m app.main
```

## Production Recommendation
- Host app on Scalingo
- Use one `worker`
- Use Scalingo PostgreSQL addon
- Keep Google Sheets as reporting only

Detailed deployment guide:
- [DEPLOY_SCALINGO.md](C:\Users\bakwi\OneDrive\Desktop\job_bot\DEPLOY_SCALINGO.md)

## CSV format for drivers
Headers:
`unit_number,first_name,last_name` or `unit,first_name,last_name`

Example:
```csv
unit_number,first_name,last_name
1001,John,Doe
1002,Ali,Karimov
```

## Notes.
- Bot uses long polling (`worker` process), so no webhook setup required.
- If a driver has already submitted at least one answer in the current quarter, the bot blocks a second submission for that driver.
- Google Sheets writes to:
  - `Survey_Wide`
  - `Drivers_Status`

## Survey_Wide Columns
`q1..q5` correspond to the current question order in [survey.json](C:\Users\bakwi\OneDrive\Desktop\job_bot\app\data\survey.json).

| Column |
|---|
| submitted_at_utc |
| survey_year |
| survey_quarter |
| survey_period_label |
| driver_id |
| telegram_user_id |
| language |
| unit_number |
| first_name |
| last_name |
| hr_q1 |
| hr_q2 |
| hr_q3 |
| hr_q4 |
| hr_q5 |
| hr_feedback |
| safety_q1 |
| safety_q2 |
| safety_q3 |
| safety_q4 |
| safety_q5 |
| safety_feedback |
| hos_q1 |
| hos_q2 |
| hos_q3 |
| hos_q4 |
| hos_q5 |
| hos_feedback |
| claims_contact |
| claims_q1 |
| claims_q2 |
| claims_q3 |
| claims_q4 |
| claims_q5 |
| claims_feedback |
| fleet_q1 |
| fleet_q2 |
| fleet_q3 |
| fleet_q4 |
| fleet_q5 |
| fleet_feedback |
| dispatch_q1 |
| dispatch_q2 |
| dispatch_q3 |
| dispatch_q4 |
| dispatch_q5 |
| dispatcher_1_name |
| dispatcher_2_name |
| dispatcher_3_name |
| dispatcher_1_rating |
| dispatcher_2_rating |
| dispatcher_3_rating |
| dispatch_feedback |
| accounting_q1 |
| accounting_q2 |
| accounting_q3 |
| accounting_q4 |
| accounting_q5 |
| accounting_feedback |
| management_q1 |
| management_q2 |
| management_q3 |
| management_q4 |
| management_q5 |
| management_feedback |
