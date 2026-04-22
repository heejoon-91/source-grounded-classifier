# User Command Examples

[한국어](commands.ko.md) | English

These are natural-language commands a user can give to an agent using this skill. They are not shell commands. The agent should interpret the request, inspect the provided data, and choose the safe workflow described in `SKILL.md`.

## Discovery / Profiling

| User command | Agent behavior |
|---|---|
| `Analyze the classification structure in this CSV dataset` | Profile the CSV, identify ID/text/category-like columns, summarize null rates, top values, and likely overloaded fields. No classification output is generated unless requested. |
| `Find columns in this JSON file that could work as categories` | Flatten/load JSON, profile fields, score category-like columns, and explain which columns are reliable or noisy. |
| `Check whether this DB table can be classified` | Inspect table schema and sample rows, identify existing labels/tags/status fields, and assess whether rule-based classification is feasible. |
| `Find the table to classify from this dump file` | Restore the dump only into a temporary DB/schema, inspect tables, and propose likely target tables. Never restore into production or mutate source data. |

## Taxonomy / Axis Design

| User command | Agent behavior |
|---|---|
| `Design better derived columns for this dataset` | Discover semantic axes from evidence and objective. Propose derived classification columns or a staging table schema. |
| `Redesign the taxonomy for search and filtering` | Optimize axes for search/filter behavior. Separate overloaded fields into searchable dimensions. |
| `Design a tag structure for recommendations` | Optimize axes for recommendation signals. Identify target, need-state, compatibility, function, risk, or preference dimensions when supported by data. |
| `Classify this from the start as one primary category plus attribute tags` | Use `taxonomy_design.strategy=representative_plus_attributes`. Make the primary axis single-value/required, and split secondary types and cross-cutting attributes into separate axes. |
| `Evaluate whether the existing category/subcategory fields are good enough` | Compare existing category-like fields against samples/top values and identify mixed semantic axes, sparse tags, inconsistent naming, or unclear values. |
| `Also explain why you created these columns` | Include each generated column's purpose, source evidence, single/multi-value policy, and review behavior in the result report. |

## Rule Authoring

| User command | Agent behavior |
|---|---|
| `Create rules.json from these criteria` | Create a project-specific rules file using `templates/rules.template.json` and `references/rule_schema.md`. Rules must cite data evidence in the response. |
| `Classify this with rules only, without a model` | Write deterministic keyword/regex/exact/numeric rules and explain confidence/review behavior. No ML model is introduced. |
| `Send ambiguous rows to manual review` | Set conservative confidence, conflict handling, and `auto_accept_threshold` so uncertain rows become `needs_review`. |
| `Explain what this rule captures` | Explain each rule's axis, value, match criteria, evidence columns, confidence, and expected false-positive risks. |

## Classification Output

| User command | Agent behavior |
|---|---|
| `Return a new file with classification columns appended` | Run or propose `scripts/classify_dataset.py`. Create an enriched copy with `classified_*` columns. Never overwrite the original source file. |
| `Create a separate file with only classification results` | Run or propose `scripts/apply_rules.py`. Create a sidecar classification CSV with row ID, axis values, confidence, evidence, rule IDs, and review status. |
| `Load the classification output into a DB staging table` | Generate sidecar output, then use `scripts/create_staging_table.py` to load it into a staging table. Do not update the source table. |
| `Create a table in the new schema defined by the rules` | Run or propose `scripts/create_derived_table.py`. Create a separate derived table with minimal identity columns, rule-axis columns, and audit columns, excluding source classification columns that the new schema replaces. |
| `Run the whole flow from taxonomy design to final classified data` | Internally profile, design axes, write rules, apply rules, validate, and return the final derived file/table plus a short report. Do not make the user run each stage separately. |
| `Pick only one representative category and put the rest into tag columns` | Validate the representative/secondary/attribute axis contract before creating derived output; if it fails, fix the rule design first. |
| `Keep only goods_name and the new classification columns in a CSV` | Create a derived CSV with minimal display columns and rule-defined columns. Do not include source classification columns such as `category/subcategory` when they are replaced by derived axes. |
| `Create a validation report for the classification results` | Run or propose `scripts/validate_classification.py` and summarize fill rate, rule counts, conflicts, review status, unmatched rows, and low-confidence samples. |
| `Return the final output with column rationale` | Create the final derived file/table and return a short report explaining why each derived column was generated. |

## Iteration / Improvement

| User command | Agent behavior |
|---|---|
| `Review needs_review rows and improve the rules` | Inspect low-confidence/unmatched/conflict samples, propose rule changes, rerun classification into a new output, and compare validation reports. |
| `Find rules that are likely to misclassify rows` | Review broad keywords, high-volume rules, conflicts, and suspicious samples; recommend tighter criteria or negative conditions. |
| `Compare these results with the previous version` | Compare two classification outputs by row ID, axis values, review status, confidence, and rule IDs. Report changed rows and likely causes. |
| `Create only a production rollout plan` | Produce a staged rollout/migration plan. Do not mutate source data. Include backup, review, validation, and rollback steps. |

## Safety / Privacy

| User command | Agent behavior |
|---|---|
| `Profile this while hiding sensitive information` | Use redaction/no-sample options and avoid printing sensitive sample values. |
| `Do not touch the original file; only create results` | Enforce output-only behavior. Refuse in-place writes and create sidecar or enriched copy. |
| `Do not update the DB source table; create staging only` | Create or update only a staging table. Explicitly avoid `UPDATE`, `DELETE`, `TRUNCATE`, or source table schema changes. |

## Minimal User Input Template

```markdown
Classify this dataset.

- source_type:
- source:
- id_column:
- text_columns:
- existing_label_columns:
- objective:
- desired_output: final_derived_file / derived_table / staging_table / report_only
- derived_identity_columns:
- privacy constraints:
```

If the user provides only a file or table, infer what is safe and ask only for missing information that blocks progress.
