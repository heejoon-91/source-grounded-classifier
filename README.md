# Dataset Taxonomy Designer

[한국어](README.ko.md) | English

Dataset Taxonomy Designer is a Codex skill for analyzing existing `category`, `tag`, `type`, `status`, or `label` fields, redesigning them into a more useful classification structure, and producing rule-based classification outputs safely.

The core goal is simple:

> Keep the original data unchanged, inspect the actual dataset, design better derived classification columns and rules, then return the result as a separate file or staging table.

This is not a product-only skill. It can be used for support tickets, documents, orders, reviews, content, equipment, logs, or any dataset where existing classification fields are overloaded, inconsistent, sparse, or not useful for downstream work.

This skill is not meant to make the user run several cleanup stages manually. The agent handles profiling, axis design, rule authoring, rule application, and validation internally, then returns the final classified dataset and a short result report as one user-facing process.

For recommendation-oriented reclassification, the standard flow is:

```text
1. Inspect the original data and identify available attributes.
2. Redefine those attributes as new columns that are useful for LLM-assisted recommendation.
3. Create a new table with the new columns, keeping only required source identifiers/display fields such as product ID and product name.
```

The new table should be a thin canonical derived table, not a copy of the full source table with extra classification columns attached.

## When To Use It

Use this skill when:

- Existing `category` / `subcategory` fields do not work well for search or recommendation.
- One column mixes product type, lifecycle, function, status, format, or business collection semantics.
- Each domain needs a different classification structure.
- You want explainable rule-based classification before training a model.
- You want staging outputs without directly changing the source DB or source file.
- You need to separate auto-classified rows from rows that require human review.

## Example

Assume a product row currently looks like this:

```text
pet_type    = ["강아지"]
category    = ["사료", "습식관"]
subcategory = ["전연령", "주식캔"]
```

The existing fields mix several meanings:

- `강아지`: target species
- `사료`: product family
- `습식관`: display or collection grouping
- `전연령`: life stage
- `주식캔`: product form

This skill guides the agent to split those meanings into derived classification output:

```json
{
  "species": ["강아지"],
  "primary_category": "사료",
  "life_stage": ["전연령"],
  "food_form": ["주식캔"],
  "display_collection": ["wet_food_zone"]
}
```

Column names and axis count are not fixed. The agent should infer them from the dataset's columns, value distribution, null rates, samples, and objective.

## Default Classification Design

The default design is not one broad multi-value category. For search, recommendation, cleanup, analytics, or derived table work, the skill guides the agent to classify in this shape from the start:

```text
one representative primary axis   single-value, required or review_if_empty
optional secondary axes           single-value, narrower subtypes
optional attribute axes           multi-value cross-cutting attributes such as function, audience, lifecycle, status, format, material, risk, or collection
```

For product data, `primary_category` should choose one best main category, while lifecycle, health function, commercial status, and format belong in separate attribute axes. For other domains, the same rule applies with domain-specific names, such as `primary_issue_type`, `primary_content_type`, or `primary_event_type`.

This contract is represented by `taxonomy_design.strategy = representative_plus_attributes`, and the derived output script validates the structure before writing results.

## Output Value Policy

Classification values in the final dataset should preserve labels observed in the source data whenever possible.

```text
Good:  primary_category = 사료
Avoid: primary_category = food
```

Use English slugs for technical identifiers such as `rule_id`, filenames, and internal metadata only. User-facing derived output values should preserve the source data's language and controlled vocabulary.

## What The Skill Does Internally

1. Inspects the dataset structure.
   - ID columns
   - title/description/content columns
   - existing category/tag/status/label columns
   - null-heavy columns
   - multi-value columns
   - overloaded semantic columns

2. Diagnoses current classification problems.
   - Synonyms or inconsistent naming
   - Multiple semantic axes packed into one field
   - Categories that are too broad for search or recommendation
   - Sparse or unreliable tags

3. Designs new classification axes.
   - Required core taxonomy columns
   - Optional attribute/tag columns
   - Single-value axes
   - Multi-value axes
   - Axes that should route missing values to review

4. Writes deterministic rules.
   - exact value
   - keyword
   - regex
   - numeric range
   - `all_of`, `any_of`, `none_of`
   - confidence
   - review behavior

5. Produces derived outputs without mutating the source.
   - sidecar CSV
   - enriched copy
   - validation report
   - DB staging table
   - rule-defined derived table

## How To Use

Users can give natural-language requests:

```text
Analyze the classification structure in this CSV dataset.
```

```text
Redefine this DB table's category/subcategory fields into better derived columns.
```

```text
Do not touch the original data. Return only a staging table.
```

```text
Keep only goods_name and return a table shaped by the new rule-defined classification columns.
```

```text
Send ambiguous rows to needs_review instead of auto-classifying them.
```

The agent follows the `SKILL.md` workflow internally. The user does not need to execute these steps one by one.

```text
1. Profile the dataset
2. Diagnose existing classification problems
3. Design new semantic axes
4. Write rules
5. Generate classification output
6. Create a validation report
7. Return the final derived file/table and a short report
```

For more examples, see [English command examples](references/commands.md) or [Korean command examples](references/commands.ko.md).

## Supported Inputs

The skill is designed to work with:

```text
csv
json
jsonl
postgres_table
postgres_dump
sqlite
```

DB dumps should be restored only into a temporary DB/schema for inspection, never directly into production or the original source DB.

## Output Shape

Typical artifacts are listed below. The primary user-facing deliverable is the `derived_output` file or DB derived/staging table; rules, schema, and reports are supporting artifacts for auditability and reproducibility.

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

The result report should include a rationale for each generated column:

```text
column name
- why it was created
- which source columns, value distributions, or samples justified it
- whether it is single-value or multi-value
- how missing or ambiguous values are handled
```

For DB-backed work, prefer a staging table:

```text
classification_staging
- source_row_id
- taxonomy_version
- axis_values
- confidence
- evidence
- rule_ids
- review_status
- missing_required_axes
- classified_at
```

Important output fields:

| Field | Meaning |
|---|---|
| `axis_values` | The derived classification values intended for use. |
| `evidence` | Rule-level evidence explaining why values were assigned. |
| `confidence` | Rule-based confidence score. |
| `rule_ids` | Stable IDs of rules that matched. |
| `review_status` | Review state such as `auto_accepted` or `needs_review`. |
| `missing_required_axes` | Required classification axes that could not be filled. |

When the user asks for data in the new schema defined by the rules, create a derived output. In this mode, do not copy every source column. Keep only minimal identity/display columns and the derived rule-axis columns.

```text
derived_classification_table
- source_row_id
- minimal source identity/display columns such as product_id, sku, goods_name, title
- one column per rule axis
- taxonomy_version
- confidence
- review_status
- classified_at
```

Detailed evidence can be written separately:

```text
classification_audit
- source_row_id
- axis_values
- conflicts
- missing_required_axes
- rule_ids
- evidence
- classified_at
```

For product data, source columns such as `pet_type`, `category`, `subcategory`, and `health_concern_tags` are excluded from top-level derived output when they are replaced by new classified columns. Traceability remains in `evidence`.

## Safety Model

The most important rule:

> Never directly modify the original source data.

By default, this skill does not:

- overwrite source CSV files
- `UPDATE` source DB tables
- `DELETE` source DB rows
- `TRUNCATE` source DB tables
- directly alter source schemas

The safe path is:

```text
source data -> profile -> apply rules -> separate output file/staging table
```

If the user wants to promote results into the source schema, that should be handled later through a separate migration or ETL plan with explicit approval.

## What It Is Good At

- Splitting overloaded category/subcategory fields into meaningful derived columns
- Designing classification structures for search, recommendation, analytics, or cleanup
- Producing explainable rule-based classification without a trained model
- Separating automatic results from rows needing human review
- Preserving the original data while experimenting
- Keeping rule, confidence, and evidence data for auditability

## Limitations

- It cannot reliably infer values that are not supported by the data.
- Rule-based classification has limits for ambiguous semantic judgment.
- The taxonomy/schema `version` is not a user-facing cleanup stage. It is an internal tracking label for rules and outputs for a dataset.
- Complex image understanding, long-form text interpretation, and review sentiment may require LLMs, embeddings, or ML classifiers.
- `auto_accepted` does not mean "guaranteed correct"; it means the current rules found no conflict or missing required axis.

## Main Files

| File | Purpose |
|---|---|
| `SKILL.md` | Runtime instructions loaded by Codex when the skill is used. |
| `references/rule_schema.md` | English rule schema reference. |
| `references/rule_schema.ko.md` | Korean rule schema reference. |
| `references/commands.md` | English user command examples. |
| `references/commands.ko.md` | Korean user command examples. |
| `templates/rules.template.json` | Starting template for project-specific classification rules. |
| `scripts/profile_dataset.py` | Profiles datasets safely. |
| `scripts/apply_rules.py` | Creates sidecar classification output. |
| `scripts/classify_dataset.py` | Creates enriched output copies. |
| `scripts/validate_classification.py` | Validates classification output. |
| `scripts/create_staging_table.py` | Loads classification results into a staging table. |
| `scripts/create_derived_table.py` | Creates derived CSV/JSON/DB tables with rule axes expanded into real columns. |

## Rule Format

See [English rule schema](references/rule_schema.md) or [Korean rule schema](references/rule_schema.ko.md).

## One-Line Summary

This skill is not a tool for blindly assigning categories. It is a classification design workflow that helps an agent inspect the data, decide which derived columns are needed, write explainable rules, and return safe classification outputs.
