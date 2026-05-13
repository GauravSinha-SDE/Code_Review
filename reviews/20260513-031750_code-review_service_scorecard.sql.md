# Review: `code-review/service_scorecard.sql`

_Generated: 2026-05-13T03:18:35.778835+00:00_

---

## Summary

This is a large Snowflake SQL view for a transportation management service scorecard. It contains multiple CTEs aggregating shipment, tracking, tender, and stop data. The query has significant bugs, logic errors, performance problems, and maintainability issues that would produce incorrect results in production.

---

## Issues

### Bugs & Logic Errors

- **[CRITICAL]** `TOTAL_MILES` uses `DISTANCE_IN_MILE_TOTAL * 0.621371` (miles-to-km conversion) but the column is labeled `TOTAL_MILES`; `TOTAL_KILOMETERS` then stores raw `DISTANCE_IN_MILE_TOTAL` — the labels and formulas are swapped, producing completely wrong distance values
- **[CRITICAL]** `CTE_LTD` uses `ROW_NUMBER() OVER(PARTITION BY LOAD_LEG_ID ORDER BY SUM(BASE_VOLUME) DESC)` — window functions cannot wrap aggregate functions; this will error or produce undefined behavior; `SUM` requires a `GROUP BY` first
- **[CRITICAL]** `BUSINESS` and `BUS_UNIT` are column aliases defined in the same SELECT list and then referenced in `CASE WHEN BUSINESS IS NULL THEN BUS_UNIT` — forward references to aliases in the same SELECT are not valid SQL and will fail or produce NULL silently in Snowflake
- **[CRITICAL]** `CTE_COL_SELECT` has a trailing comma before `FROM` (`SEL.DEDICATED_CARRIER_FLAG,\n\nFROM SC_LOG...`) — this is a syntax error that prevents the view from compiling
- **[CRITICAL]** `LATE_MARKER_TYPE` logic: `DESTINATION_ARRIVAL_ONTIME_STOP_COUNT <> 0 AND CAPS_EARLY_STOP_COUNT = 0` implies "late," but a non-zero on-time count indicates on-time delivery, not late — the condition is inverted and will misclassify most shipments
- **[WARN]** `TT.SHIPMENT_NUMBER AS CAPS_DELIVERED_STOP_COUNT` — aliasing a shipment number as a delivered stop count is semantically incorrect and will produce nonsensical count values downstream
- **[WARN]** `CTE_STOP_CNT` uses `SUM(DISTINCT ...)` over window partitions — `SUM(DISTINCT)` deduplicates numeric values before summing, so two stops with the same count value (e.g., both = 1) will be summed as 1 instead of 2, silently undercounting
- **[WARN]** `LOAD_AT_CORPORATE_ID_1 = 'RM'` and `= 'RF'` in `ORDER_TYPE` CASE — these compare an 8+ character corporate ID column to 2-character strings; the `SUBSTR` check used in `SHIPMENT_TYPE` is not applied here, creating inconsistent logic
- **[WARN]** `CTE_APPOINT_SEL` selects `FIRST_APPOINTMENT_NOTIFIED` and `FIRST_APPOINTMENT_CONFIRMED` with no deduplication; if multiple appointment records exist for an origin stop, the join in `CTE_GET_CNT` will fan out rows before the `MIN()` window collapses them, potentially inflating counts
- **[WARN]** `ORIGIN_ARRIVAL_ONTIME_INDICATOR` is derived via `MIN()` on a string ('Y'/'N') — `MIN('Y','N') = 'N'` — so any single late leg makes the whole load "not on time," which may be intentional but is undocumented and fragile
- **[WARN]** `TRIM(EXTENDED_ATTRIBUTES_TMS:SHPM_REFERENCE_NUMBER_22, '""""')` — the trim character string `""""` contains 4 double-quote characters; the intent appears to be trimming a single `"` but the escaping is inconsistent and may not strip quotes correctly
- **[WARN]** `CONVERT_TIMEZONE('America/Los_Angeles','UTC',LT.CC_UPDATED_DATETIMESTAMP)` in the WHERE clause converts a UTC timestamp *to* LA time, then compares it to a UTC cutoff — this introduces a systematic ±8/9 hour filter offset, potentially missing or double-including records near the boundary
- **[INFO]** Comment on `ORIGIN_ADDRESS_KEY` says "Addres Key" (typo) — minor but indicates copy-paste generation of column comments

### Performance & Scalability

- **[CRITICAL]** `CTE_GET_CNT` repeats a 40+ column `PARTITION BY` clause identically across ~25 window functions — Snowflake will evaluate each as a separate sort/partition pass; this should be replaced with a `GROUP BY` plus aggregation or a single `QUALIFY` deduplication step
- **[CRITICAL]** The correlated subquery in the WHERE clause of `CTE_COL_SELECT` executes three nested scalar subqueries against `UCMF.UTILITIES` metadata tables on every row evaluation — this will serialize execution and severely degrade performance on large datasets
- **[WARN]** `CTE_GET_CNT` joins `T_TD_GBL_SC_TMS_LOAD_TRANSPORT_DETAIL` again (aliased `LD`) without filtering — this table is already used in `CTE_LTD`; the second unbounded join re-scans the full detail table and fans out rows before the window deduplicates them
- **[WARN]** `SELECT DISTINCT` in the final SELECT is used as a correctness patch for row fan-out caused by undeduped joins in `CTE_GET_CNT` — this is an expensive anti-pattern masking upstream join problems
- **[WARN]** `CTE_STOP_DIST_SEL` performs a `ROW_NUMBER()` with `ORDER BY STP.CC_UPDATED_DATETIMESTAMP ASC` after `STOP_ID DESC` — the ascending timestamp ordering after descending ID is contradictory and the intent is ambiguous, potentially picking the wrong stop
- **[INFO]** View includes a `LATE_MARKER_TYPE` column that also contains business logic (`CASE WHEN`) — this type of computation belongs in a reporting layer or materialized table, not a base view queried repeatedly

### Architecture & Maintainability

- **[WARN]** Large hardcoded `IN` lists of shipping location codes (100+ values) for `BUSINESS_UNIT` classification are embedded directly in the view — these should live in the lookup table (`T_GBL_BY_CONFIG_LKP`) already used elsewhere in the view
- **[WARN]** `CTAS_REGION` and `CTAS_CUST_GRP` are named with the `CTAS_` prefix (Create Table As Select) but are CTEs — naming is misleading and inconsistent with other CTE names
- **[WARN]** `CC_CREATED_DATETIMESTAMP` and `CC_UPDATED_DATETIMESTAMP` are set to `CURRENT_TIMESTAMP()` in the view — these audit fields are meaningless in a view and will always reflect query time, not record creation/update time
- **[WARN]** `LOAD_LEG_KEY` is computed as `HASH(LT.LOAD_LEG_ID,'BY')` — hash collision risk is unaddressed; no uniqueness constraint or salt strategy is documented
- **[INFO]** The commented-out `GROUP BY` line in `CTE_STOP_CNT` (`--GROUP BY LOAD_LEG_KEY,...`) indicates the query was refactored from GROUP BY to window functions but the comment was left in, suggesting incomplete cleanup
- **[INFO]** `SPACEMAKER` is a meaningful business flag but the column comment only says "If Shipment Reference Is In 'ZUSM' And 'ZNSM'" — the business purpose is undocumented

---

## Suggestions

- Fix the miles/km column swap: apply `* 1.60934` for km or `* 0.621371` for miles and correct the column names accordingly
- Replace the `BUSINESS`/`BUS_UNIT` forward-alias reference with a nested subquery or second CTE that resolves both values before the final CASE
- Remove the trailing comma before `FROM` in `CTE_COL_SELECT`
-
