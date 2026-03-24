# Driver Import CSV Structure

Use this exact header for the next import file:

```csv
unit_number,first_name,last_name,dispatcher_1_first_name,dispatcher_1_last_name,dispatcher_2_first_name,dispatcher_2_last_name,dispatcher_3_first_name,dispatcher_3_last_name,is_active
```

## Field Rules
- `unit_number`: required
- `first_name`: required
- `last_name`: required
- `dispatcher_1_first_name`: optional
- `dispatcher_1_last_name`: optional
- `dispatcher_2_first_name`: optional
- `dispatcher_2_last_name`: optional
- `dispatcher_3_first_name`: optional
- `dispatcher_3_last_name`: optional
- `is_active`: required, use `1` for active and `0` for inactive

## Important Rules
1. If a dispatcher is assigned, both first and last name must be filled.
2. If a driver has only one dispatcher, leave dispatcher 2 and 3 fields empty.
3. If a driver has no dispatcher yet, leave all dispatcher fields empty.
4. Do not change the column order.
5. Keep one driver per row.
6. Team drivers on the same unit must still be separate rows.

## Example
```csv
unit_number,first_name,last_name,dispatcher_1_first_name,dispatcher_1_last_name,dispatcher_2_first_name,dispatcher_2_last_name,dispatcher_3_first_name,dispatcher_3_last_name,is_active
0001,John,Doe,Alex,Smith,Maria,Lopez,,,1
0002,Jane,Roe,David,Kim,,,,,1
0003,Bob,Stone,,,,,,,1
```

The file template is stored here:
- [DRIVERS_IMPORT_TEMPLATE.csv](C:\Users\bakwi\OneDrive\Desktop\job_bot\DRIVERS_IMPORT_TEMPLATE.csv)
