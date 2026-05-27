# Review: `code-review/service_scorecard.sql`

_Generated: 2026-05-27T07:34:57.435211+00:00_

---

## Summary

Large, complex Snowflake view with multiple CTEs building a service scorecard. Contains several logic bugs, performance problems, security concerns, and maintainability issues. The code is functional but has meaningful correctness flaws.

## Issues

**Bugs & Logic Errors**

- [CRITICAL] `TOTAL_KILOMETERS` is assigned `LT.DISTANCE_IN_MILE_TOTAL` (miles value) — `TOTAL_MILES` correctly converts with `* 0.621371`, but the kilometer column contains the raw miles value with no conversion
- [CRITICAL] `LATE_MARKER_TYPE` logic is inverted: `DESTINATION_ARRIVAL_ONTIME_STOP_COUNT <> 0` means on-time stops exist, yet labels it 'Delivered Late'; the condition should test for late-stop counts, not on-time counts
- [CRITICAL] `SUM(DISTINCT ...)` in `CTE_STOP_CNT` is unreliable — `SUM(DISTINCT 1)` returns 1 regardless of how many qualifying rows exist; should be `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` without DISTINCT
- [WARN] `CAPS_DELIVERED_STOP_COUNT` is mapped from `TT.SHIPMENT_NUMBER` — column name mismatch suggests wrong source column; a shipment number is not a delivered stop count
- [WARN] `CONSIGNEE_CORPORATE_ID_1` checks `LOAD_AT_CORPORATE_ID_1 = 'RM'` but the RECFIBER branch uses `'RF'` — the NULL guard only covers 'RF', leaving potential NULL for 'RM' inbound
- [WARN] `FIRST_TENDER_ACCEPTANCE_COUNT` is set to 0/1 per row but is never aggregated (no SUM/MAX in `CTE_GET_CNT`), so for multi-tender loads the value is arbitrary depending on which `R_NO=1` row survives
- [WARN] `ORDER_TYPE` ELSE clause redundantly falls through to `'CUSTOMER'` — the preceding WHEN already covers `'5'`/`'9'` as `'CUSTOMER'`, making the ELSE unreachable but misleading
- [WARN] `BUSINESS` and `BUS_UNIT` are intermediate aliases referenced in a later `CASE WHEN BUSINESS IS NULL THEN BUS_UNIT` — this relies on Snowflake allowing column-alias forward references within the same SELECT, which is non-standard and fragile
- [WARN] `CTE_APPOINT_SEL` uses `MIN(APP.APPOINTMENT_FROM_DATE_TIME) OVER(PARTITION BY APP.APPOINTMENT_KEY)` — partitioning by appointment key rather than load leg key means the first notification per appointment, not per load, which may pull cross-load values
- [WARN] `CTE_STOP_DIST_SEL` orders by `STOP_ID DESC, CC_UPDATED_DATETIMESTAMP ASC` — descending STOP_ID for latest but ascending timestamp for earliest is contradictory; likely should both be DESC

**Performance & Scalability**

- [CRITICAL] `WHERE` clause contains four correlated subqueries against `UCMF.UTILITIES` tables executed per-row in the main filter — these should be pre-computed as a CTE or variable
- [WARN] `CTE_COL_SELECT` contains a nested CTE (`WITH CTE_PIVOT AS (WITH cte_load_transport AS (...))`) — nested CTEs inside a CTE body are non-standard; most engines materialise them separately and it hinders the optimiser
- [WARN] `CTE_STOP_CNT` computes ~10 window functions over the same `PARTITION BY LOAD_LEG_ID` in a single pass; Snowflake handles this but the upstream `CTE_STOP_CAL` already deduplicates with `ROW_NUMBER`, then `CTE_GET_CNT` re-aggregates the same counts with `MIN()` — triple-aggregation is wasteful
- [WARN] `CTE_COL_SELECT` is referenced six times in `CTE_GET_CNT` (SEL, CAL→STOP_CAL→STOP_CNT, TED, AP, LD, STP) — if not materialised, this CTE is evaluated multiple times over the large base table
- [WARN] `CONVERT_TIMEZONE` applied to `LT.CC_UPDATED_DATETIMESTAMP` in the WHERE clause prevents index/clustering key pruning on that column
- [WARN] `LEFT JOIN CTE_LTD LD ON LD.LOAD_LEG_ID = SEL.LOAD_LEG_ID` in `CTE_GET_CNT` re-joins the LTD CTE that was already joined in `CTE_COL_SELECT`, causing a redundant join

**Security**

- [WARN] Hard-coded `HASH(LT.LOAD_LEG_ID,'BY')` surrogate key — if the hashing seed `'BY'` is known, surrogate key collision or enumeration is possible; document the algorithm and access controls
- [INFO] No row-level security or column masking on PII-adjacent fields (`SHIPMENT_FROM_NAME`, corporate IDs, location codes) — depends entirely on database-level grants

**Architecture & Maintainability**

- [WARN] Massive inline hard-coded `IN` lists of location codes (100+ values each for CONSUMER/KCP) should be externalised to a lookup/reference table; any update requires DDL on this view
- [WARN] `CC_CREATED_DATETIMESTAMP` and `CC_UPDATED_DATETIMESTAMP` are both set to `CURRENT_TIMESTAMP()` in the view — since this is a view (not a table load), these stamps change every query execution, making them meaningless for audit or incremental load tracking
- [WARN] `GROUP BY ALL` (Snowflake extension) hides which columns are actually being grouped vs. aggregated — makes correctness review and future refactoring difficult
- [INFO] Typo in view column comment: `ORIGIN_ADDRESS_KEY` comment reads `'Origin Addres Key'` (missing 's')
- [INFO] Comment on `CTE_STOP_DIST_SEL` reads "This Is To G Distance" — incomplete sentence
- [INFO] Mixed use of `SUBSTR` and `SUBSTRING` for the same operation throughout

## Suggestions

- Externalise the CONSUMER/KCP location code lists into `TMS.STAGING.T_GBL_BY_CONFIG_LKP` alongside existing lookups, then JOIN instead of using IN-lists
- Pre-materialise the incremental load timestamp via a `SET` variable or a leading CTE before the main query to eliminate the four correlated subqueries in the WHERE clause
- Fix `TOTAL_KILOMETERS` to multiply `DISTANCE_IN_MILE_TOTAL` by `1.60934` (or rename the column to avoid the incorrect label)
- Replace `SUM(DISTINCT CASE WHEN ... THEN 1 ELSE 0 END)` with `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` throughout `CTE_STOP_CNT`
- Consider converting this to a materialised/dynamic table to cache the expensive multi-CTE scan and make the `CC_CREATED_DATETIMESTAMP` semantically meaningful
