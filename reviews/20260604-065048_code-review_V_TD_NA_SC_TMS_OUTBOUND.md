# Review: `code-review/V_TD_NA_SC_TMS_OUTBOUND`

_Generated: 2026-06-04T06:51:18.833134+00:00_

---

## Summary

Snowflake SQL view for TMS outbound logistics data. Multiple critical and notable issues found across correctness, security, performance, and maintainability.

## Issues

- **[CRITICAL]** Trailing comma after `ACTUAL_LINEHAUL` expression (line ~`COALESCE(LC.PAYMENT_AMOUNT,...) AS ACTUAL_LINEHAUL,`) before `FROM` clause causes a syntax error; view will not compile
- **[CRITICAL]** `TRIM(LT.EXTENDED_ATTRIBUTES_TMS:CURRENT_OPERATIONAL_STATUS_ID,'""""')` used as join key to `ST.STATUS_ID` without type-casting the semi-structured variant — implicit cast may silently fail or produce wrong matches
- **[CRITICAL]** Zone join conditions (`OZC`, `DZC`) use raw `EXTENDED_ATTRIBUTES_TMS:FIRST_CITY_NAME` (unquoted variant, no TRIM) while `SELECT` trims them — mismatched representations will cause join failures/missed matches
- **[CRITICAL]** Correlated subquery in `WHERE` clause executes up to 3 nested scalar subqueries against `UCMF.UTILITIES` per row evaluation — O(n) subquery storm; will not scale and may cause full table scans on every execution
- **[WARN]** `SELECT DISTINCT` on the outer query with no clear deduplication key — masking upstream data quality issues (noted in `CTE_SHIP_LOC` comment); `DISTINCT` is a code smell that hides root cause
- **[WARN]** `CTE_SHIP_LOC` uses `MAX(SHIPPING_LOCATION_KEY)` to arbitrarily resolve duplicates — comment admits it's a "temporary fix"; arbitrary key selection may return wrong location data silently
- **[WARN]** `INNER JOIN CTE_SHIP_LOC LCD ON LCD.SHIPPING_LOCATION_KEY = LT.DESTINATION_SHIPPING_LOCATION_KEY` — INNER JOIN will silently drop load legs with no matching destination shipping location, potentially hiding data
- **[WARN]** `CONVERT_TIMEZONE('America/Los_Angeles','UTC',LT.CC_UPDATED_DATETIMESTAMP)` converts FROM LA TO UTC — argument order in Snowflake is `(source_tz, target_tz, timestamp)`; this is backwards if the stored timestamp is already UTC
- **[WARN]** `WEEK(TO_DATE(...))` uses Snowflake's default week mode which starts Sunday — undocumented assumption; ISO week number vs. calendar week may differ, leading to incorrect reporting
- **[WARN]** `DISTANCE_IN_MILE_TOTAL*0.621379` — conversion factor is slightly imprecise (standard is 0.621371); minor but accumulates over many records
- **[WARN]** `SCALED_WEIGHT_TOTAL*2.20462261307789` — excessive precision in literal suggests copy-paste from external source; no rounding applied before storage
- **[WARN]** `LT.TENDER_RESPONSE_OVERRIDE_AMOUNT AS ACTUAL_CHARGE_AMOUNT` — using an "override" field as the primary charge amount with no fallback or validation is semantically risky
- **[WARN]** `LEFT JOIN SC_MD.INT_SC_MD.T_MD_GBL_SC_TMS_DIVISION DI` followed by `WHERE DI.DIVISION_CODE = 'KCNA'` — LEFT JOIN negated by WHERE predicate; effectively an INNER JOIN, misleading and potentially confusing the optimizer
- **[WARN]** `AND LT.FIRST_SHIPPING_LOCATION_CODE LIKE ('2%')` — filtering on a leading wildcard-free LIKE is fine, but parentheses around the literal are misleading style
- **[INFO]** `'BY' AS CC_SOURCE_SYSTEM` and `'UTC' AS CC_TIMEZONE` are hardcoded constants — undocumented magic strings; should reference a config table or constant
- **[INFO]** `TRIM(...,'""""')` repeated 15+ times — unclear intent (trimming literal quote chars vs. escaped quotes); should be encapsulated in a macro or UDF
- **[INFO]** `LD` subquery (`SELECT DISTINCT LOAD_LEG_KEY FROM T_TD_GBL_SC_TMS_LOAD_TRANSPORT_DETAIL`) used only for INNER JOIN filtering — equivalent to `EXISTS`/`IN` subquery but less clear; optimizer may handle it poorly without statistics
- **[INFO]** No `NULL` handling for `CONCAT(OZC.ZONE_CODE,'-',DZC.ZONE_CODE)` — if either zone is unmatched (LEFT JOIN), `LANE` silently becomes `null-null` or `null` depending on Snowflake concat behavior
- **[INFO]** View references another view `SC_LOG.INT_TMS.V_MD_NA_SC_TMS_CUSTOMER_HIERARCHY` — stacked views increase query compilation time and make execution plans opaque
- **[INFO]** No column-level lineage or transformation documentation beyond comments; unit conversion rationale and source system assumptions should be in a README or data dictionary

## Suggestions

- Replace the 3-level nested scalar subquery with a pre-materialized config table join or a parameterized stored procedure with the watermark logic extracted outside this view
- Fix the LEFT JOIN + WHERE anti-pattern on `DI.DIVISION_CODE` by changing it to `INNER JOIN SC_MD.INT_SC_MD.T_MD_GBL_SC_TMS_DIVISION DI ON ... AND DI.DIVISION_CODE = 'KCNA'`
- Standardize variant field extraction with explicit `::STRING` casting and a helper UDF to replace the repeated `TRIM(...,'""""')` pattern
- Address the duplicate `SHIPPING_LOCATION_KEY` root cause in the source table rather than relying on `MAX()` workaround in every consuming view
- Add `TRY_TO_DATE()` instead of `TO_DATE()` for variant-sourced date strings to prevent view-breaking parse failures on bad data
