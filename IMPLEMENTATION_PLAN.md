# Dispatch Survey Implementation Plan

## Why This Plan Is Separate
`requirements.txt` must contain only Python dependencies. If we place instructions there, package installation will break. This plan is intentionally stored in a separate document so the project remains deployable and maintainable.

## Goal
Build a stable production version of the Telegram survey bot where:
- the bot is deployed as a single Python worker;
- PostgreSQL is the source of truth;
- Google Sheets is the reporting layer;
- each driver can have 0-3 assigned dispatchers;
- each assigned dispatcher is evaluated separately by name;
- the data model supports quarterly surveys and future growth without redesign.

## Core Architecture
Use the minimum stable stack:
- Telegram Bot: `aiogram`
- Application runtime: one worker process
- Primary database: PostgreSQL
- Reporting/export: Google Sheets
- Driver import source: CSV only as an import file, not as a runtime database

Production data flow:
1. Driver list is imported from CSV into PostgreSQL.
2. Bot reads driver and dispatcher assignments from PostgreSQL.
3. Driver completes the survey in Telegram.
4. Survey answers are saved to PostgreSQL first.
5. Completed survey is exported to Google Sheets.
6. Management tracks completion and scores in Google Sheets or SQL reports.

## Design Principles
1. PostgreSQL is the source of truth.
2. Google Sheets is not the main database.
3. CSV remains only an import/update format.
4. Avoid extra services unless they solve a real operational problem.
5. Keep one deployable app and one managed database.
6. Design schema for quarterly surveys, not one-off forms.

## Target Deployment Model
Recommended production topology:
- Hosting: Scalingo app
- Process type: `worker`
- Database: Scalingo PostgreSQL addon
- Secrets: environment variables only
- Google credentials: service account JSON in env var or mounted file path

Do not use in production:
- SQLite as primary DB
- CSV as live source of driver truth
- Google Sheets as only data storage
- multiple polling workers for one bot token

## Required Domain / Webhook Decision
For the current project, keep polling at first release.
Reason:
- current bot already fits a worker model;
- deployment is simpler;
- no domain is required;
- fewer moving parts.

Webhook can be considered later only if there is a strong operational reason.

## Data Model Changes

### 1. Drivers
Move all driver identity and assignment data into PostgreSQL.

Table: `drivers`
- `id` PK
- `unit_number` text not null
- `first_name` text not null
- `last_name` text not null
- `is_active` boolean not null default true
- `language_default` text nullable
- `created_at`
- `updated_at`

Recommended uniqueness rule:
- unique on `(unit_number, first_name, last_name)`

Reason:
- one unit may have team drivers;
- one unit can map to multiple active drivers;
- a single unique unit is not enough.

### 2. Dispatchers
Do not store dispatcher names inside survey answers as the primary structure. Create a separate dispatcher entity.

Table: `dispatchers`
- `id` PK
- `first_name` text not null
- `last_name` text not null
- `is_active` boolean not null default true
- `created_at`
- `updated_at`

Recommended uniqueness rule:
- unique on `(first_name, last_name)` unless there is a better internal dispatcher identifier

If you have internal employee IDs, use them. That is preferable.

### 3. Driver-Dispatcher Assignment
A driver can have up to 3 dispatchers. Do not create `dispatcher_1`, `dispatcher_2`, `dispatcher_3` columns in the `drivers` table if we want a durable design.

Correct structure:

Table: `driver_dispatchers`
- `id` PK
- `driver_id` FK -> drivers.id
- `dispatcher_id` FK -> dispatchers.id
- `slot_number` integer not null
- `is_active` boolean not null default true
- `created_at`
- `updated_at`

Rules:
- `slot_number` allowed values: 1, 2, 3
- unique on `(driver_id, slot_number)`
- unique on `(driver_id, dispatcher_id)` for active assignments

Reason:
- this still supports exactly 3 display positions in the bot;
- avoids schema rewrite if assignment logic changes;
- easier to import and update.

If you insist on 3 physical fields in one table, that is possible, but it is a worse long-term design. The relational assignment table is the correct architecture.

### 4. Survey Runs
Table: `survey_runs`
- `id` PK
- `driver_id` FK -> drivers.id
- `telegram_user_id` nullable or linked user id
- `survey_year` integer not null
- `survey_quarter` integer not null
- `status` text not null
- `started_at`
- `completed_at`
- `language`
- `unit_number_snapshot`
- `first_name_snapshot`
- `last_name_snapshot`
- `created_at`
- `updated_at`

Recommended uniqueness rule:
- unique on `(driver_id, survey_year, survey_quarter)` if exactly one submission per quarter is required

Reason:
- quarter must be explicit in schema;
- snapshots preserve historical correctness if driver data changes later.

### 5. Survey Responses
Keep responses normalized.

Table: `survey_responses`
- `id` PK
- `survey_run_id` FK -> survey_runs.id
- `department_code` text not null
- `question_code` text not null
- `answer_value` text not null
- `answer_text` text nullable
- `related_dispatcher_id` nullable FK -> dispatchers.id
- `related_dispatcher_name_snapshot` nullable text
- `created_at`

Reason:
- general questions and dispatcher-specific questions can live in one table;
- `related_dispatcher_id` marks answers that belong to a specific dispatcher;
- dispatcher name snapshot keeps history if names later change.

## Dispatcher Question Design
Current business requirement:
- if a driver has 2 or 3 dispatchers, we ask an additional score question for each assigned dispatcher;
- question format should be similar to: `How do you rate Dispatcher Name Lastname from 1-10?`

Recommended implementation:
1. Keep the normal Dispatch department block.
2. After standard Dispatch questions, dynamically generate one question per assigned dispatcher.
3. For each dispatcher:
   - show dispatcher full name;
   - ask one 1-10 rating question;
   - store answer with:
     - `department_code = dispatch`
     - `question_code = dispatcher_rating`
     - `related_dispatcher_id = dispatcher.id`
     - `related_dispatcher_name_snapshot = full name`
     - `answer_value = 1..10`

Why this is correct:
- no need to hardcode three different question codes in the base catalog;
- supports 0, 1, 2, or 3 dispatchers cleanly;
- reporting remains simple.

Optional future improvement:
- add one optional comment per dispatcher only if needed later.
Do not add this now unless there is a real reporting need.

## Google Sheets Redesign
Google Sheets should be wide-format for management visibility, but the export must be generated from PostgreSQL, not treated as source truth.

### Sheet Strategy
Use two sheets only:
1. `Survey_Wide`
2. `Drivers_Status`

Do not add more sheets unless a clear reporting need appears.

### Sheet 1: Survey_Wide
One completed survey = one row.

Base columns:
- submitted_at_utc
- survey_year
- survey_quarter
- survey_period_label
- driver_id
- telegram_user_id
- language
- unit_number
- first_name
- last_name

Department columns:
- hr_q1
- hr_q2
- hr_q3
- hr_q4
- hr_q5
- safety_q1
- safety_q2
- safety_q3
- safety_q4
- safety_q5
- hos_q1
- hos_q2
- hos_q3
- hos_q4
- hos_q5
- claims_contact
- claims_q1
- claims_q2
- claims_q3
- claims_q4
- claims_q5
- fleet_q1
- fleet_q2
- fleet_q3
- fleet_q4
- fleet_q5
- dispatch_q1
- dispatch_q2
- dispatch_q3
- dispatch_q4
- dispatch_q5
- accounting_q1
- accounting_q2
- accounting_q3
- accounting_q4
- accounting_q5
- management_q1
- management_q2
- management_q3
- management_q4
- management_q5

Dispatcher assignment snapshot columns:
- dispatcher_1_name
- dispatcher_2_name
- dispatcher_3_name

Dispatcher rating columns:
- dispatcher_1_rating
- dispatcher_2_rating
- dispatcher_3_rating

Department feedback columns:
- hr_feedback
- safety_feedback
- hos_feedback
- claims_feedback
- fleet_feedback
- dispatch_feedback
- accounting_feedback
- management_feedback

Reason:
- managers can filter in one sheet;
- each dispatcher has a stable named column set;
- no need to parse normalized SQL data manually in Sheets.

Important:
`dispatcher_1_name` etc. are export columns only. They do not replace the relational DB design.

### Sheet 2: Drivers_Status
One active driver = one row.

Columns:
- driver_id
- unit_number
- first_name
- last_name
- is_active
- dispatcher_1_name
- dispatcher_2_name
- dispatcher_3_name
- current_period_submitted
- current_period_submitted_at
- current_period_status

Use case:
- instantly see who answered and who did not.

## Driver Import Strategy
CSV import should update these tables:
- `drivers`
- optionally `dispatchers`
- optionally `driver_dispatchers`

Recommended input model for CSV:
- unit_number
- first_name
- last_name
- dispatcher_1_first_name
- dispatcher_1_last_name
- dispatcher_2_first_name
- dispatcher_2_last_name
- dispatcher_3_first_name
- dispatcher_3_last_name
- is_active

Import behavior:
1. Upsert driver by `(unit_number, first_name, last_name)`
2. Upsert each dispatcher by identity
3. Replace active dispatcher assignments for that driver according to CSV
4. Mark removed assignments inactive

Reason:
- CSV remains simple for operations staff;
- DB stays normalized.

## Survey Logic Changes
New survey flow should be:
1. Driver chooses language
2. Driver enters unit number
3. Driver selects themselves from driver list
4. Bot starts current quarter survey run
5. Standard departments run in order
6. Dispatch department standard questions run
7. Bot reads assigned dispatchers for the selected driver
8. For each assigned dispatcher, bot asks one rating question by name
9. Optional department feedback questions continue as currently designed
10. Bot completes survey
11. Data is saved to PostgreSQL
12. Completed row is exported to Google Sheets
13. `Drivers_Status` is updated

## Operational Rules
1. Save to PostgreSQL first.
2. Export to Sheets after transaction commit.
3. If Sheets export fails, mark export status and retry later.
4. Do not block survey completion because of a Sheets failure.

Recommended support table:
Table: `survey_exports`
- `id`
- `survey_run_id`
- `target` (`survey_wide`, `drivers_status`)
- `status`
- `last_attempt_at`
- `error_message`

This is optional but strongly recommended for production stability.

## Deployment Plan

### Phase 1. Schema Preparation
1. Move from SQLite production usage to PostgreSQL.
2. Create PostgreSQL schema for:
   - drivers
   - dispatchers
   - driver_dispatchers
   - survey_runs
   - survey_responses
   - optional survey_exports
3. Add indexes and unique constraints.
4. Define quarter-based uniqueness.

Deliverable:
- stable PostgreSQL schema ready for imports and survey traffic

### Phase 2. Import and Data Migration
1. Prepare new CSV format with dispatcher columns.
2. Write importer logic for drivers and dispatcher assignments.
3. Validate duplicates and inactive assignments.
4. Load active production driver list into PostgreSQL.

Deliverable:
- all active drivers and dispatchers stored in DB

### Phase 3. Bot Logic Update
1. Replace SQLite production connection with PostgreSQL.
2. Load driver and dispatcher assignments from DB.
3. Add dynamic dispatcher rating questions.
4. Preserve existing quarter lock logic.
5. Keep one-time 1-10 scale notice.

Deliverable:
- bot works against production schema

### Phase 4. Google Sheets Redesign
1. Replace current export mapping with new `Survey_Wide` structure.
2. Add `Drivers_Status` export.
3. Export dispatcher names and dispatcher ratings into fixed columns.
4. Add retry-safe export logic.

Deliverable:
- management can monitor completion and scores in Sheets

### Phase 5. Production Deployment
1. Create Scalingo app.
2. Add PostgreSQL addon.
3. Configure env vars:
   - BOT_TOKEN
   - DATABASE_URL or SQLAlchemy-compatible DB URL
   - GOOGLE_SHEET_ID
   - GOOGLE_SERVICE_ACCOUNT_JSON
4. Deploy as one `worker` process.
5. Run DB setup/migrations.
6. Import drivers CSV into production DB.
7. Start bot.

Deliverable:
- live production bot backed by PostgreSQL

### Phase 6. Post-Launch Validation
1. Test one survey with 0 dispatchers.
2. Test one survey with 2 dispatchers.
3. Test one survey with 3 dispatchers.
4. Verify PostgreSQL writes.
5. Verify Google Sheets export.
6. Verify `Drivers_Status` completion tracking.
7. Verify duplicate quarter submission behavior.

Deliverable:
- production confidence before broad rollout

## What Not To Do
1. Do not store dispatchers as plain text fields only in survey rows.
2. Do not keep production driver truth only in CSV.
3. Do not write directly to Google Sheets without storing in PostgreSQL first.
4. Do not keep SQLite as the long-term production DB.
5. Do not add extra services like Redis, queues, dashboards, or BI tools at this stage.

## Final Recommended State
At the end of implementation, the stable architecture should be:
- one Telegram bot app;
- one PostgreSQL database;
- one Google Sheets reporting file;
- one CSV import workflow for driver updates.

That is enough for a clean, reliable first production version.

## Next Execution Order
When implementation starts, use this exact order:
1. finalize schema;
2. finalize CSV format for dispatchers;
3. implement PostgreSQL models and migrations;
4. rewrite import flow;
5. add dynamic dispatcher survey logic;
6. redesign Google Sheets export;
7. test locally;
8. deploy to Scalingo;
9. load production drivers;
10. run pilot.
