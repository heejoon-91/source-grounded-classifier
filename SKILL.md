---
name: source-grounded-classifier
description: Use when a dataset has category, type, tag, label, segment, status, or classification fields that may be overloaded, inconsistent, sparse, or unsuitable for downstream search, recommendation, analytics, routing, or reporting. This skill does not assume domain-specific categories; it profiles the dataset, discovers semantic axes from evidence, designs one representative primary axis plus atomic one-property columns when supported, and returns sidecar/enriched outputs or staging tables without directly modifying the original source data.
metadata:
  short-description: Design rule-based dataset taxonomies from evidence
---

# Dataset Taxonomy Designer

Use this skill to turn messy or overloaded classification fields into a clearer, domain-specific taxonomy and rule-based staging pipeline. The goal is not to carry a fixed category list. The goal is to inspect the data, discover useful semantic axes, write explicit rules, and apply them safely.

## Input Contract

Ask for or infer these fields:

- `source_type`: `csv`, `json`, `jsonl`, `postgres_table`, `postgres_dump`, `sqlite`
- `source`: file path, DB table, or dump path
- `id_column`: stable row identifier
- `text_columns`: title/name/description/content fields
- `existing_label_columns`: category/tag/type/status fields, if any
- `objective`: search, recommendation, analytics, routing, cleanup, compliance, or unknown
- `write_mode`: `report_only`, `output_file`, `staging_table`, or `derived_table`
- `recommendation_mode` when objective is recommendation: `related_items`, `similar_items`, `bundle_cross_sell`, `personalized_ranking`, `search_filtering`, or unknown
- `must_have_axes` when known: axes that downstream recommendation cannot work without

`write_mode` is an execution detail, not a staged user workflow. Infer it from the request:

- If the user asks to analyze or evaluate only, use `report_only`.
- If the user asks to clean, reclassify, return data, or create a new schema from rules, produce the final output in one pass as an `output_file` by default. For DB sources, export the target rows and create the final rule-shaped CSV unless the user explicitly asks for a DB table.
- If any of `source`, `id_column`, or `objective` is missing, infer only when obvious. Otherwise ask one concise blocking question.

For user-facing command examples, see `references/commands.md` or `references/commands.ko.md`.

## User-Facing Contract

The user should experience this skill as one process that returns the final requested artifact. The internal workflow can profile data, diagnose fields, design axes, author rules, run classification, validate results, and write outputs, but do not expose those as steps the user must manually approve unless a safety boundary requires it.

Default behavior for a cleanup/classification request:

1. Infer the target output.
2. Run the internal workflow end to end.
3. Return the final derived CSV file plus a short report. Create a DB staging/derived table only when explicitly requested.

For recommendation-oriented reclassification, use this standard sequence:

1. Inspect the original data to identify available attributes and overloaded source fields.
2. Define new columns that make those attributes useful for LLM-assisted recommendation, retrieval, filtering, ranking, exclusion, or review.
   - Default to one semantic property per column.
   - Do not put multiple unrelated source values into one broad tag column such as `subcategory_tag`.
   - Split overloaded source values into atomic columns such as `life_stage`, `food_form`, `health_concern`, `display_collection`, `target_species`, `size_class`, or domain-specific equivalents.
3. Create a new CSV output with those new columns, keep only required source identifiers/display fields such as product ID and product name, and fill the new columns from the original row evidence.

Supporting files such as rules, schema, validation reports, and exports may be created for auditability, but they are supporting artifacts. The primary deliverable is the final classified dataset requested by the user.

The report must explain the full evidence chain from original values to derived columns. It is not enough to list final columns. Include:

- original value inventory: source classification columns inspected, distinct counts, null/empty counts, full unique individual value lists with counts, and top observed values with counts.
- semantic bucket analysis: how original values were grouped into meaning buckets such as primary class, lifecycle, form factor, item type, health/function, target audience, collection/status, or review signal.
- column decision rationale: for every generated column, why that column exists, which original values or source columns justify it, and why it is separate from other columns.
- value policy: which single semantic property the column represents, whether the output is single-value by default, how multiple candidate values are prioritized, and why any multi-value exception is needed.
- result inventory: for every generated column, the produced values, counts, empty count, fill rate, and representative examples.
- review behavior: whether missing or ambiguous values become `needs_review` or remain intentionally empty because the source lacks that property.

## Safety Rules

- Never directly modify, overwrite, delete, truncate, or update the original source data.
- Return a report, sidecar classification file, enriched copy, or staging table instead.
- If the user asks to "apply" results, create a separate migration/update plan or staging output and require an explicit follow-up approval before any source mutation outside this skill workflow.
- `scripts/classify_dataset.py` refuses to write output over the source file.
- For DB dumps, restore only into a temporary database/schema first.
- Keep raw source values. Store normalized classifications as derived results.
- Preserve source-language labels in user-facing derived values. Do not translate labels to English or invent English slugs for output values when the dataset already contains usable category/tag names.
- Use stable English or ASCII identifiers only for technical fields such as `rule_id`, filenames, or internal metadata when helpful. The axis value written into the final classified dataset should come from observed source values or a clearly documented source-language normalization.
- Every proposed axis and rule must cite evidence: column names, top values, sample rows, null rates, or downstream use.
- Route ambiguous or low-confidence rows to review instead of forcing labels.
- Redact sensitive sample columns when profiling PII, secrets, health, financial, or customer-support data.

## Workflow

This workflow is internal to the agent. Execute it end to end for the chosen `write_mode`; do not stop at a plan when enough information exists to produce the final output safely.

1. **Profile the source**
   - Inspect schema, row count, candidate ID fields, text fields, category-like fields.
   - Measure null rates, distinct counts, top values, and representative samples.
   - For every original category-like or tag-like column, create an inventory of observed values with counts. For array/list columns, count both raw combinations and individual values.
   - Include the full list of unique individual values for every original classification/tag column in the report, not only the unique count or top values. If the list is very long, place the complete list in a supporting artifact and link it from the report.
   - Use `scripts/profile_dataset.py` for CSV/JSON/JSONL/PostgreSQL when helpful.
   - Use `scripts/inspect_postgres_schema.py` after restoring a PostgreSQL dump to choose the target table.
   - Use `--redact-columns` or `--no-samples` when sample values may contain sensitive data.

2. **Diagnose current classifications**
   - Find overloaded columns: one column containing multiple semantic axes.
   - Find sparse or noisy columns: high null rate, high cardinality, inconsistent names, packed multi-values.
   - Find useful signals: repeated title patterns, controlled vocabularies, existing labels, metadata, descriptions.

3. **Discover semantic axes**
   - Do not assume domain categories.
   - Infer axes from evidence and objective.
   - Examples of possible axes, not defaults: product type, audience, form factor, lifecycle, function, channel, urgency, root cause, material, region, risk, status, collection.
   - Drop axes that do not improve the stated objective.
   - Use the default design contract for cleanup/search/recommendation/derived-table work:
     - Create one representative primary axis when the data supports it. Name it for the domain, such as `primary_category`, `primary_issue_type`, `primary_content_type`, or `canonical_status`.
     - The representative axis must be `multi_value: false` and should be `required: true` or `review_if_empty: true`.
     - Create optional secondary axes for narrower subtypes, such as `secondary_category`, `issue_subtype`, or `content_format`.
     - Put cross-cutting meanings into separate atomic attribute axes, such as audience, function, lifecycle, status, compatibility, material, channel, risk, or collection.
     - Default every derived output column to `multi_value: false`.
     - Use one column for one semantic property. Do not create broad catch-all columns like `subcategory_tag`, `attribute_tags`, or `misc_tags` when source values can be split into specific attributes.
     - If one source field contains `전연령`, `주식캔`, `체중조절`, and `습식관`, split them into columns such as `life_stage`, `food_form`, `health_concern`, and `display_collection` instead of one multi-value tag column.
     - When a row has multiple values for the same property, either choose one canonical single value with documented priority, map it to one observed combined value such as `공용` when supported by the data, or create explicit boolean/flag columns such as `supports_dog` and `supports_cat`.
     - Allow `multi_value: true` only when the user explicitly requests multi-label output or when the property is inherently multi-valued and cannot be represented without information loss; document the exception in the report.
     - Do not finish with only one broad multi-label axis when the data contains a clear primary class plus additional attributes.
   - Before writing rules, profile overloaded source values and group them into semantic buckets:
     - product family or primary class
     - subtype or item type
     - lifecycle or age stage
     - form factor or package/form
     - health/function/need state
     - target audience/species/compatibility
     - collection/display/status/business flags
   - Record the semantic bucket table in the report:
     - original values in the bucket
     - source columns where they appeared
     - count/coverage
     - resulting derived column
     - rationale for grouping or excluding values
   - Separate core taxonomy columns from optional atomic attribute columns:
     - Core taxonomy columns should be useful for primary search, filtering, routing, analytics, or reporting.
     - Optional atomic attributes can be sparse when the source data only supports them for some rows.
   - For cleanup/search/analytics objectives, the single-value representative axis is the default, not a later cleanup step.
     - Do not use one broad multi-label axis when the data contains hierarchy or different semantic levels. Split it into representative category, subcategory/item type, and atomic attribute columns.
     - Enforce disjoint value ownership between the representative axis and attribute axes. If a source value is assigned to an attribute axis such as `display_collection`, `life_stage`, `food_form`, or `health_function`, do not also allow that same value as a representative primary value.
     - When the source primary/category field contains only an attribute-like value, create an explicit fallback rule from other row evidence before output. If no evidence exists, leave the representative axis empty and route the row to review instead of copying the attribute value into the representative axis.
   - Decide and document for every axis whether it is:
     - `required`: missing values should route the row to review.
     - `optional`: empty values are acceptable because the source lacks evidence.
     - `single_value`: exactly one best value should be selected.
     - `multi_value`: exceptional; all supported values should be retained only with explicit justification.
   - Document why each axis exists. Tie each axis to an observed source problem, such as overloaded labels, repeated top values, sparse tags, or a downstream search/recommendation need.
   - Create a short candidate column design before writing rules. Prefer the design that gives high coverage on core axes without hiding useful sparse attributes inside a catch-all tag column.

4. **Choose storage strategy**
   - Prefer a separate CSV output for all sources, including DB tables and DB dumps.
   - Create a DB staging/classification table only when the user explicitly asks for DB loading.
   - For DB cleanup, default to flat derived CSV columns for user-facing fields plus a separate audit file for detailed evidence.
   - When the user asks for "the data in the new classified schema", use a derived CSV output unless they explicitly ask for a DB table:
     - Keep only minimal identity/display columns such as `source_row_id` and a human-readable name/title when available.
     - Drop source classification columns from top-level output when they are replaced by derived axes.
     - Expand rule axes into real output columns.
     - Keep only minimal operational audit columns in the new table by default: `taxonomy_version`, `confidence`, `review_status`, and `classified_at`.
     - Put detailed audit payloads such as `axis_values`, `missing_required_axes`, `rule_ids`, and `evidence` in a separate audit output unless the user explicitly asks to keep them in the derived table.
     - Treat the derived CSV as a thin canonical output, not a reduced copy of the source table.
   - Only propose adding source columns when the schema owner wants derived fields in the main table.

5. **Author rules**
   - Start with deterministic rules: exact values, normalized strings, keyword dictionaries, regexes, existing label mappings.
   - Assign each rule a `rule_id`, target `axis`, target `value`, evidence columns, confidence, and review behavior.
   - Use observed source labels as output `values` whenever possible. For Korean source data, output Korean labels; for English source data, output English labels; for mixed source data, preserve the source's dominant controlled vocabulary.
   - If aliases must be merged, choose the canonical value from an observed source label, not an arbitrary translation.
   - Use `references/rule_schema.md` or `references/rule_schema.ko.md` for the portable JSON rule format.
   - Start from `templates/rules.template.json` to avoid malformed rules.
   - Fill `taxonomy_design.strategy` as `representative_plus_atomic_attributes` unless the user explicitly asks for a different design.
   - Fill `taxonomy_design.representative_axis`, `secondary_axes`, and `attribute_axes` before running derived output creation.
   - Attribute axes in the default strategy should be single-value atomic columns. If an attribute axis is multi-value, add a `multi_value_exception` note explaining why it cannot be split safely.

6. **Apply rules to staging**
   - Use `scripts/apply_rules.py` to create a sidecar classification CSV.
   - Use `scripts/classify_dataset.py` to create a new enriched data file with classification columns appended.
   - Use `scripts/create_derived_table.py` when the user wants data returned in the rule-defined schema instead of a generic `axis_values` payload.
   - For DB sources, export rows to CSV and apply rules. Stop at CSV output by default.
   - For DB derived outputs, use `scripts/create_derived_table.py --output ...csv` by default; use `--dsn ... --table ...` only when the user explicitly requests a DB table.
   - When producing a DB-oriented CSV, include a PostgreSQL DDL helper file for creating the destination table unless the user asks for files only.
   - Use `scripts/create_derived_table.py --audit-output ...` when detailed evidence should be preserved outside the thin derived table.
   - Use `derived_output.identity_columns` or `--identity-columns` to keep only required source fields such as product ID, product number, SKU, title, or product name.

7. **Validate**
   - Compare counts: source rows vs classified rows.
   - Sample high-confidence and low-confidence rows.
   - Report unmatched rows, conflicting rules, and suspicious top values.
   - Report missing required axes separately from optional empty axes.
   - Report fill rate for every derived column as `filled rows / total rows`; explain that optional empty values can be expected when the source has no evidence for that property.
   - Report top produced values and counts for every derived column.
   - Validate semantic disjointness before final delivery: representative primary axis values must not contain values owned by atomic attribute axes. If overlap exists, fix rules and regenerate output in the same run; do not ask the user to manually post-process it.
   - Core axes should not be considered successful just because another optional axis matched.
   - Use `scripts/validate_classification.py` to generate fill-rate, rule-count, conflict, and review-status summaries.
   - For production use, require human review for low confidence or conflicting outputs.

8. **Promote**
   - Promote only reviewed/stable outputs through a separately approved migration or ETL job.
   - Keep `taxonomy_version` and `rule_version`.
   - Preserve rollback path: old output file, backup table, or dump.
   - Do not perform source mutation as part of the default skill flow.

## Decision Guidance

Use rule-only classification when:

- Patterns are visible in existing fields.
- Category names or tags are explicit but poorly organized.
- The goal requires explainability and repeatability.
- Labeled training data is not available.

Use LLM or model assistance only for:

- Axis design from ambiguous samples.
- Low-confidence rows after deterministic rules.
- Attribute extraction where keyword rules are insufficient.
- Later phases after reviewed labels exist.

## Output Shape

Provide these sections in the final answer:

1. Final Output
2. Original Value Inventory
3. Semantic Bucket Analysis
4. Derived Column Decisions
5. Result Column Inventory
6. Rule Design Summary
7. Validation Results
8. Supporting Artifacts
9. Risks and Open Decisions

When creating artifacts, prefer:

```text
classification/
  taxonomy_axes.json
  rules.json
  classified_output.csv
  staging_output.csv
  derived_output.csv
  derived_schema.json
  validation_report.json
```

For DB-backed projects, still prefer CSV artifacts by default:

```text
classification/
  product_source.csv
  derived_output.csv
  derived_table.postgres.sql
  classification_audit.csv
  validation_report.json
```

When explicitly requested, a DB staging table may use:

```text
classification_staging
- source_row_id
- taxonomy_version
- axis_values jsonb
- derived flat columns for core axes, when needed by the app or analyst
- confidence numeric
- evidence jsonb
- rule_ids text[]
- review_status
- missing_required_axes text[]
- classified_at
```

When the user asks for the final cleaned schema, prefer:

```text
derived_classification_csv
- source_row_id
- minimal source identity/display columns such as product_id, sku, product_name, title
- one representative single-value primary axis
- optional secondary single-value axes
- optional atomic attribute columns, one semantic property per column
- minimal operational audit columns: taxonomy_version, confidence, review_status, classified_at
```

For detailed audit, prefer a separate artifact:

```text
classification_audit
- source_row_id
- taxonomy_version
- axis_values
- confidence
- review_status
- conflicts
- missing_required_axes
- rule_ids
- evidence
- classified_at
```
