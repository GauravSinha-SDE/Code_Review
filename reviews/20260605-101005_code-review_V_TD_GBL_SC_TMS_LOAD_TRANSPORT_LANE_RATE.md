# Review: `code-review/V_TD_GBL_SC_TMS_LOAD_TRANSPORT_LANE_RATE`

_Generated: 2026-06-05T10:10:38.738426+00:00_

---

## Summary

This is a Snowflake view that builds a transport lane rate dataset by joining multiple staging tables, computing a first-postal-code heuristic, and filtering on an incremental load watermark. There are several critical correctness, performance, and maintainability issues.

---

## Issues

- **[CRITICAL]** `TRANS_MILES_SEL` labels `AVG(DISTANCE_IN_MILE_TOTAL)` as `TOTAL_KILOMETERS` and `AVG(DISTANCE_IN_MILE_TOTAL * 0.621379)` as `TOTAL_MILES` — the aliases are **swapped**; multiplying by 0.621379 converts km→miles but the column is named kilometers, and vice versa
- **[CRITICAL]** The `WHERE` clause filters only on `T.CC_UPDATED_DATETIMESTAMP`, but the driving table `TFF_T` is joined via `LEFT JOIN` to `BY_LANE_ASSC_T`, `BY_RATE_T`, etc. — records with updated child rows (e.g. rates changed) but unchanged `TFF_T` timestamp will be **silently missed** by the incremental filter
- **[CRITICAL]** `SELECT DISTINCT` on the final query with a `HASH(...)` PK does not guarantee uniqueness if any of the hash inputs (`LANE_ASSC_ID`, `TFF_CD`, `RATE_ID`, `EFCT_DT`, `RNG_RATE_ID`) are NULL — `HASH(NULL, ...)` collapses distinct rows into the same key value in Snowflake
- **[CRITICAL]** The WHERE subquery references `V_TD_GBL_SC_TMS_LOAD_TRANSPORT_LANE_RATE` (this very view) inside `SOURCE_TABLE_VIEW` — if the view is being created/replaced, this self-reference may resolve to stale or missing metadata causing the watermark to always return NULL and default to `1901-01-01`, forcing full scans every run
- **[WARN]** `FST_POSTAL_CD` uses `YEAR(SHIPPED_DATE) >= YEAR(CURRENT_TIMESTAMP()) - 1` — this is **not a rolling 1-year window**; in January it includes almost two calendar years; use `SHIPPED_DATE >= DATEADD(year, -1, CURRENT_DATE())` instead
- **[WARN]** `TRANS_LD_SEL` and `TRANS_MILES_SEL` CTEs scan `T_TD_GBL_SC_TMS_LOAD_TRANSPORT` (potentially very large) with no partition/date filter beyond the `FST_POSTAL_CD` year filter, causing full table scans on every view query
- **[WARN]** Three correlated scalar subqueries inside the `WHERE IFNULL(...)` clause execute on every row evaluation; they should be materialized once (e.g. via a CTE or separate lookup)
- **[WARN]** `LEFT JOIN TMS.STAGING.BY_RATE_T R ON LA.TFF_ID = R.TFF_ID AND LA.RATE_CD = R.RATE_CD` — joining on `RATE_CD` (a descriptive code) rather than a surrogate key is fragile and may produce unintended fan-out if `RATE_CD` is not unique within a tariff
- **[WARN]** `LIKE ANY CN.CODE_VALUE` on `CTE_CNFG_TBL` (lines joining `CN` and `CN1`) — `CODE_VALUE` is a scalar string being used as a pattern array; this only works if the column contains a Snowflake array literal, which is non-obvious and fragile if data format changes
- **[WARN]** `SELECT DISTINCT` on a wide multi-join result set is a code smell masking an underlying fan-out/duplicate problem from the joins (particularly `RNG_RATE_T` and `CTE_CNFG_TBL`); the root cause should be fixed rather than suppressing duplicates
- **[WARN]** `SHIPMENT_MODE` CASE: the first two WHEN branches (`CN.CODE_DESCRIPTION IS NOT NULL`, `CN1.CODE_DESCRIPTION IS NOT NULL`) can both be non-null simultaneously due to two separate left joins on the same config table — precedence is arbitrary and could produce incorrect mode classification
- **[WARN]** Zone description cleanup (`LIKE 'KC in %'`, `LIKE '% KCP'`, etc.) is hardcoded business logic in a view — this will require DDL changes for every new pattern and should live in the config lookup table
- **[INFO]** `TRIM(LT.EXTENDED_ATTRIBUTES_TMS:LANE_ASSOCIATION_ID, '""""')` — the quad-quote trim character is unusual; confirm this correctly strips the intended characters from the semi-structured JSON path extraction
- **[INFO]** `CC_CREATED_DATETIMESTAMP` and `CC_UPDATED_DATETIMESTAMP` both emit `CURRENT_TIMESTAMP()` — in a view these will always reflect query time, not actual record creation/update time, making them misleading for audit purposes
- **[INFO]** The comment on the view body ends with `'...Nhas Context Menu'` — appears to be a copy-paste artifact from a UI tooltip
- **[INFO]** Magic constant `'BY'` is repeated throughout (hash salt, source system literal) with no named constant or explanation; document its meaning

---

## Suggestions

- Fix the miles/kilometers alias swap immediately and add a unit test against a known distance
- Replace `YEAR(SHIPPED_DATE) >= YEAR(CURRENT_TIMESTAMP()) - 1` with `SHIPPED_DATE >= DATEADD(year, -1, CURRENT_DATE())`
- Extract the three watermark subqueries into a single CTE `WATERMARK_CTE` evaluated once
- Add NULL-safe handling to the `HASH(...)` PK (e.g. use `COALESCE` on each input or use `SHA2` with explicit separators)
- Investigate and eliminate the root fan-out cause rather than relying on `SELECT DISTINCT`
- Move zone-description cleanup patterns into `T_GBL_BY_CONFIG_LKP` so they are data-driven
