# Review: `code-review/T_TD_GBL_SC_TMS_INBOUND`

_Generated: 2026-06-04T06:50:02.467459+00:00_

---

## Summary

Snowflake DDL for a TMS inbound staging/integration table. Schema is mostly functional but has several data modeling, documentation, and design issues worth addressing.

## Issues

- **[WARN]** `DISTANCE_IN_MILE_TOTAL NUMBER(38,0)` — integer precision loses fractional miles; should be `NUMBER(15,2)` or similar
- **[WARN]** `TOT_SCLD_WGT NUMBER(11,4)` and `MAX_VOLUME NUMBER(11,4)` use inconsistent precision/scale compared to `ACTUAL_CHARGE_AMOUNT NUMBER(15,2)` and `ACTUAL_LINEHAUL NUMBER(15,2)` — no documented standard for numeric precision across the table
- **[WARN]** `WEEK_NUM NUMBER(38,0)` — `NUMBER(38,0)` is the Snowflake max; semantically a small integer (1–53); oversized type obscures intent and wastes no storage but misleads readers
- **[WARN]** `LAST_STATE_CODE VARCHAR(100)` vs `FIRST_STATE_CODE VARCHAR(50)` — same semantic field with inconsistent column widths (lines 9 vs 19)
- **[WARN]** `LAST_POSTAL_CODE VARCHAR(100)` — 100 chars is excessive for a postal code; no equivalent `FIRST_POSTAL_CODE` column creates asymmetry between origin and destination data
- **[WARN]** `ORIGIN_ADDRESS_KEY` comment says "Will Contain E Value" (line 7) — typo, likely "A Value"; indicates copy-paste documentation errors throughout
- **[WARN]** `DESTINATION_ADDRESS_KEY` comment says "For The Last Stop For The Road" (line 17) — likely "For The Load"; another documentation error
- **[WARN]** `SHIPPING_LOCATION_NAME VARCHAR(100)` (line 16) — ambiguous ownership; no `ORIGIN_` or `DESTINATION_` prefix unlike all surrounding location columns
- **[INFO]** `CC_TIMEZONE VARCHAR(3)` — 3 chars is too short for IANA timezone identifiers (e.g., `America/Chicago`); only fits abbreviations like `CST`, which are ambiguous across regions
- **[INFO]** `DAY_OF_WEEK VARCHAR(3)` and `END_DOW VARCHAR(3)` — inconsistent naming convention (one spelled out, one abbreviated); `END_DOW` has no corresponding `START_DOW` alias for `DAY_OF_WEEK`
- **[INFO]** No `AUDIT_DELETED_TIMESTAMP` or soft-delete flag — if records are logically deleted in the source, this table has no way to track that
- **[INFO]** `NUMBER_OF_STOP_TOTAL NUMBER(38,0)` — no `NOT NULL` constraint; a load should always have a countable (possibly zero) number of stops
- **[INFO]** `LOAD_LEG_ID` is nullable despite `LOAD_LEG_KEY` being the PK — if these are surrogate vs. natural key pairs, `LOAD_LEG_ID` should likely be `NOT NULL UNIQUE`
- **[INFO]** No clustering key defined — for a time-series operational table this size, clustering on `START_DATE_TIME` or `AUDIT_INSERTED_TIMESTAMP` would significantly improve query performance at scale
- **[INFO]** Table comment `'Handy Tools- Inbound Table'` (last line) is not meaningful for documentation or discovery purposes

## Suggestions

- Standardize all surrogate key columns to a consistent numeric type (e.g., `NUMBER(18,0)`) and reserve `NUMBER(38,0)` only where Snowflake sequence values genuinely require it
- Add a `FIRST_POSTAL_CODE` and `FIRST_COUNTRY_CODE` to mirror the destination fields and enforce symmetric origin/destination modeling
- Introduce a `RECORD_SOURCE VARCHAR(50)` or populate `CC_SOURCE_SYSTEM NOT NULL` and enforce it to support multi-source lineage tracing
- Define a `CLUSTER BY (START_DATE_TIME)` or `CLUSTER BY (AUDIT_INSERTED_TIMESTAMP)` for predictable micro-partition pruning on range queries
- Replace freeform table comment with a structured description including owner, source system, refresh cadence, and grain
