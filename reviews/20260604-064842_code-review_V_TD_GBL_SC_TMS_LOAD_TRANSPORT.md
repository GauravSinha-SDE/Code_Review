# Review: `code-review/V_TD_GBL_SC_TMS_LOAD_TRANSPORT`

_Generated: 2026-06-04T06:49:23.678213+00:00_

---

## Summary

This is a complex Snowflake view implementing an incremental load pattern for a TMS (Transportation Management System) load/transport entity. It involves multiple CTEs for domain lookups, deduplication workarounds, and roughly 20 joins. There are significant correctness, performance, security, and maintainability issues.

---

## Issues

- **[CRITICAL]** `BILL_TO_CUSTOMER_KEY` is aliased identically to `CUSTOMER_KEY` (`CU.CUSTOMER_KEY AS BILL_TO_CUSTOMER_KEY`) — both columns always return the same value; the bill-to customer join logic is missing entirely
- **[CRITICAL]** The watermark subquery is duplicated verbatim in both `CTE_CNVT_DT` and the final `WHERE` clause; they can diverge if the config table changes between CTE evaluation and final filter, producing inconsistent incremental windows
- **[CRITICAL]** `CTE_CNVT_DT` filters on `CC_UPDATED_DATETIMESTAMP > watermark`, but the final `FROM TMS.STAGING.BY_LD_LEG_T LLT` applies the same filter independently — rows in `CTE_DOMAIN_VAL` will be a *subset* of rows in the outer query, causing `DV.*` columns to be NULL for any row that was already in `CTE_CNVT_DT` but not re-matched (race condition between evaluations)
- **[CRITICAL]** `LEFT JOIN TMS.STAGING.CNSE_T CN ON CN.SHPG_LOC_CD = LLT.LAST_SHPG_LOC_CD` — `CNSE_T` is not deduplicated like `SHIPPING_LOCATION`; if multiple consignee rows share the same `SHPG_LOC_CD`, this silently fans out and produces duplicate output rows
- **[CRITICAL]** Same fan-out risk for `LEFT JOIN TMS.STAGING.LDAT_T DAT ON DAT.SHPG_LOC_CD = LLT.FRST_SHPG_LOC_CD` — no deduplication guard on `LDAT_T`
- **[WARN]** `CTE_SHIP_LOC` and `CTE_TRN_STOP` use `MAX(KEY)` to arbitrarily resolve duplicates — this is explicitly called a "temporary fix" in comments but is a data quality risk if keys are not semantically ordered; no ticket/deadline reference to track resolution
- **[WARN]** `HASH(LLT.LD_LEG_ID, 'BY')` used as surrogate key — Snowflake's `HASH()` is not collision-free and not a standards-compliant surrogate key strategy; same pattern on `SHIPMENT_KEY`
- **[WARN]** `CURRENT_TIMESTAMP()` emitted for both `CC_CREATED_DATETIMESTAMP` and `CC_UPDATED_DATETIMESTAMP` — a view re-evaluated at different times will return different timestamps, making these columns meaningless and breaking audit/CDC semantics
- **[WARN]** The watermark subquery uses three correlated scalar subqueries inside a scalar subquery (nested `SELECT`s for `SOURCE_KEY`, `TARGET_TABLE_ID`, `SOURCE_TABLE_ID`) — evaluated once per CTE and once in the outer WHERE; in Snowflake this is inefficient and brittle; should be a single CTE
- **[WARN]** `YEAR(AUDT_SYS_DTT) >= (YEAR(SYSDATE()) - 1)` in `CTE_AUDT_STOP` filters on a function over a column, preventing partition pruning; also silently excludes audit rows older than last year regardless of load date
- **[WARN]** `DESTINATION_POSTTAL_CODE` (double-T) is a typo in both the column declaration and the comment — will propagate to all downstream consumers
- **[WARN]** `ORIGIN_ZONE_CODE` logic hardcodes city/state string literals (`'BEECH ISLAND, SC'`, `'MENASHA'`, etc.) directly in the view — business logic embedded in view definition, no externalization or documentation of change process
- **[WARN]** `SHIPMENT_MODE` logic uses `LLT.FIXD_ITNR_DIST * 0.6213` (km→mile conversion hardcoded inline) with a magic threshold of `600` and no comment explaining the unit or business rule source
- **[WARN]** `LEFT JOIN SC_MD.INT_SC_MD.T_MD_GBL_SC_TMS_STATUS STAT ON LLT.CUR_OPTLSTAT_ID = STAT.STATUS_ID` — join column types are not verified; `CUR_OPTLSTAT_ID` is cast via `TO_NUMBER` elsewhere but used raw here
- **[WARN]** `EXTENDED_ATTRIBUTES_TMS:LIVE_LOAD_FLAG` uses Snowflake semi-structured (variant) column access with no type cast — result type is VARIANT, not STRING/BOOLEAN, which may cause downstream type issues
- **[WARN]** `CTE_AUDT_STOP` does `INNER JOIN CTE_DOMAIN_VAL DV ON AU.LD_LEG_ID = DV.LD_LEG_ID` — this restricts audit stop rows to only those LD_LEG_IDs already in the incremental window, meaning audit data for non-updated loads is never captured; intent unclear
- **[WARN]** `WHERE concat(domain_column_name, '|', domain_type_id) IN (...)` in `CTE_LD_TRAN_LKP` — the `WHERE` is applied *after* the `LEFT JOIN`, effectively converting it to an `INNER JOIN` for the domain filter; rows not matching a domain will be excluded rather than returning NULL
- **[INFO]** Commented-out columns (`--LLT.NMNL_WGT`, `--LLT.TOT_TARE_WGT`, `--DVS1.CURRENT_OPERATIONAL_STATUS_DESCRIPTION`) left in production DDL with no explanation
- **[INFO]** `SUBSTR` and `SUBSTRING` are used interchangeably in `ORIGIN_PLANT` vs `DESTINATION_PLANT` — inconsistent style
- **[INFO]** No explicit `ORDER BY` guard on `ROW_NUMBER()` tiebreaker in `CTE_AUDT_STOP` when `AUDT_SYS_DTT` values are equal — `RANK=1` pick is non-deterministic for ties
- **[INFO]** `RFRC_NUM23`, `RFRC_NUM2`, `RFRC_NUM14` column comments (`'Shipment ID / System Identifier'`, etc.) do not match the generic `RFRC_NUM` pattern; these appear to be repurposed reference number slots with no traceability to their actual source field semantics

---

## Suggestions

- **Externalize the watermark logic** into a single CTE (e.g., `CTE_WATERMARK`) referenced by both `CTE_CNVT_DT` and the outer `WHERE` to guarantee a consistent, single-evaluation cutoff
- **Deduplicate `CNSE_T` and `LDAT_T`** using the same `MAX(KEY) GROUP BY location_code` pattern already applied to `CTE_SHIP_LOC` and `CTE_TRN_STOP`, or document a cardinality guarantee
- **Fix `BILL_TO_CUSTOMER_KEY`** by adding a separate join to the customer table on the bill-to customer code (likely a different field than `CUST_CD`)
- **Replace `HASH()` surrogate keys** with `SHA2()` or a sequence-based key if collision safety is required; at minimum document the accepted collision probability
- **Move hardcoded business rules** (`ORIGIN_ZONE_CODE` city lists, `SHIPMENT_MODE` thresholds, plant prefix rules) to a reference/config table to allow updates without DDL changes
- **Cast `EXTENDED_ATTRIBUTES_TMS:LIVE_LOAD_FLAG`** explicitly (e.g., `::VARCHAR`) at the source subquery to avoid propagating VARIANT type
-
