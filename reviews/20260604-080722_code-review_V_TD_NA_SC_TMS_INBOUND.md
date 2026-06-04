# Review: `code-review/V_TD_NA_SC_TMS_INBOUND`

_Generated: 2026-06-04T08:07:56.961215+00:00_

---

## Summary

This view has multiple critical and moderate issues spanning correctness, security, performance, and maintainability. The SQL is functional in spirit but contains several antipatterns and real bugs that will cause problems at scale or under edge cases.

## Issues

- **[CRITICAL]** Trailing comma after `COALESCE(LC.PAYMENT_AMOUNT, LT.TENDER_RESPONSE_OVERRIDE_AMOUNT) AS ACTUAL_LINEHAUL,` before `FROM` is a syntax error in standard SQL; will fail on strict engines
- **[CRITICAL]** `CTE_SHIP_LOC` uses `MAX(SHIPPING_LOCATION_KEY)` as a "temporary fix" for duplicates — this silently returns an arbitrary name match and masks a data quality problem that should be resolved at source; comment even acknowledges it's a temporary fix but it appears permanent
- **[CRITICAL]** Zone joins (`OZC`, `DZC`) concatenate raw semi-structured JSON values without `TRIM`/quote-stripping, unlike all other `EXTENDED_ATTRIBUTES_TMS` references — zone lookups will silently fail or return NULLs for most rows, producing a NULL `LANE`
- **[CRITICAL]** Correlated scalar subqueries in the `WHERE` clause (the incremental load timestamp logic) execute 3 separate subqueries per row evaluation, causing catastrophic performance at any meaningful data volume; these should be pre-computed as a CTE
- **[WARN]** `SELECT DISTINCT` on the outer query is a red flag — it signals an unresolved fan-out from the joins (likely `CTE_SHIP_LOC` or zone joins) and masks duplicate rows instead of fixing the root join cardinality issue
- **[WARN]** The subquery `(SELECT DISTINCT LOAD_LEG_KEY FROM T_TD_GBL_SC_TMS_LOAD_TRANSPORT_DETAIL)` joined via `INNER JOIN` is equivalent to a semi-join but forces a full distinct scan; should use `EXISTS` or `IN` for clarity and potential optimizer benefit
- **[WARN]** `LT.EXTENDED_ATTRIBUTES_TMS:CURRENT_OPERATIONAL_STATUS_ID` used unquoted/uncast in the `INNER JOIN ON` clause to `ST.STATUS_ID` — implicit type coercion from VARIANT to the status column type may silently fail or produce wrong matches
- **[WARN]** `DISTANCE_IN_MILE_TOTAL * 0.621379` — column name says "mile" but the conversion is km→mile, yet the source column is already named `DISTANCE_IN_MILE_TOTAL`; either the source stores km with a misleading name or this conversion is applied twice
- **[WARN]** `WEEK(TO_DATE(...))` and `DAYNAME(TO_DATE(...))` each call `TRIM(...EXTENDED_ATTRIBUTES_TMS:START_DATE_TIME...)` twice — redundant parsing of the same semi-structured path; extract to a CTE or lateral alias
- **[WARN]** `LEFT JOIN DI` on `DIVISION_KEY` is used only for `WHERE DI.DIVISION_CODE = 'KCNA'` — this turns the left join into an effective inner join; should be `INNER JOIN` for clarity and to allow the optimizer to prune earlier
- **[WARN]** `TRIM(LT.EXTENDED_ATTRIBUTES_TMS:..., '""""')` — stripping four double-quote characters is unusual; if the source contains `"value"` (JSON string), the correct fix is `::STRING` casting or `PARSE_JSON`, not character trimming, which will corrupt values with legitimate leading/trailing characters
- **[WARN]** `COALESCE(LC.PAYMENT_AMOUNT, LT.TENDER_RESPONSE_OVERRIDE_AMOUNT) AS ACTUAL_LINEHAUL` — if `PAYMENT_AMOUNT` is `0` (not NULL), it returns `0` rather than the override amount; zero-value payments may be intentional but this should be explicitly documented
- **[INFO]** Comment typo on `ORIGIN_ADDRESS_KEY`: "Will Contain E Value" should be "A Value"
- **[INFO]** `CC_SOURCE_SYSTEM` hardcoded as `'BY'` and `CC_TIMEZONE` as `'UTC'` in a view — if these ever change, every downstream consumer breaks silently; these should come from a config/metadata table
- **[INFO]** `CONVERT_TIMEZONE('America/Los_Angeles','UTC', ...)` converts to UTC but then compares against `LAST_SUCCESSFUL_LOAD_DATETIME` — need to confirm that column is stored in UTC; if not, the incremental filter window is wrong
- **[INFO]** No filter on `ACTUAL_CHARGE_TYPE` case normalization in `CTE_ACT_LINEHAUL` beyond `UPPER()` — if source ever uses mixed-case variants beyond uppercase, the CTE handles it, but `CHARGE_CODE NOT IN ('ZSPT')` has no case normalization applied
- **[INFO]** View definition lacks any `CREATE OR REPLACE` idempotency guard or version comment; schema migration tooling (e.g., Flyway/Liquibase) would be unable to detect drift

## Suggestions

- Replace all `TRIM(..., '""""')` patterns with `TRY_CAST(LT.EXTENDED_ATTRIBUTES_TMS:FIELD_NAME::STRING AS ...)` for correct and safe JSON value extraction
- Extract the incremental load timestamp logic into a leading CTE (e.g., `CTE_LOAD_WATERMARK`) to run once and reference inline
- Fix zone join column expressions to apply the same quote-stripping as other fields before comparing to `OZC.ZN_DESC` / `DZC.ZN_DESC`
- File a tracked issue to resolve the duplicate `SHIPPING_LOCATION_CODE` problem at the source table rather than patching it in this view with `MAX()`
- Replace `SELECT DISTINCT` on the outer query with a proper deduplication strategy (e.g., `ROW_NUMBER()` with a defined tiebreak) once fan-out root cause is identified
