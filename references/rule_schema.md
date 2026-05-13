# Rule Schema

[한국어](rule_schema.ko.md) | English

Rules are project-specific. Keep the schema portable and explicit.

## Minimal JSON

```json
{
  "version": "taxonomy-v1",
  "id_column": "id",
  "text_columns": ["name", "description"],
  "auto_accept_threshold": 0.6,
  "default_review_status": "needs_review",
  "taxonomy_design": {
    "strategy": "representative_plus_attributes",
    "representative_axis": "primary_category",
    "secondary_axes": ["secondary_category"],
    "attribute_axes": ["function_tags", "status_tags"]
  },
  "feature_contract": {
    "retrieval_axes": ["primary_category", "secondary_category"],
    "ranking_axes": ["function_tags"],
    "filter_axes": ["primary_category"],
    "exclusion_axes": [],
    "fallback_axes": ["primary_category"]
  },
  "derived_output": {
    "identity_columns": ["name"],
    "drop_source_columns": ["category", "subcategory"],
    "audit_columns": "minimal"
  },
  "axes": {
    "axis_name": {
      "description": "What this axis means",
      "role": "primary",
      "used_for_retrieval": true,
      "used_for_ranking": true,
      "used_for_filtering": true,
      "used_for_exclusion": false,
      "feature_weight_hint": 1.0,
      "multi_value": false,
      "required": false,
      "review_if_empty": false,
      "max_values": 1,
      "values": {
        "value_name": {
          "description": "Meaning of this value",
          "confidence": 0.8,
          "priority": 0,
          "source_columns": ["name", "description"],
          "keywords": ["keyword", "phrase"],
          "negative_keywords": ["exclude this phrase"],
          "regex": ["\\bpattern\\b"],
          "exact_values": {"status": ["active", "published"]},
          "numeric_ranges": {"price": {"min": 10, "max": 100}},
          "all_of": [],
          "any_of": [],
          "none_of": [],
          "rule_id": "axis.value.keyword"
        }
      }
    }
  }
}
```

## Semantics

- `axes`: independent semantic dimensions discovered from data.
- `values`: allowed values for one axis.
- `taxonomy_design.strategy`: use `representative_plus_attributes` for the default one-pass design: one representative primary axis plus optional secondary and attribute axes.
- `taxonomy_design.representative_axis`: the single-value primary axis that best answers "what is this row mainly?"
- `taxonomy_design.secondary_axes`: optional single-value subtype axes.
- `taxonomy_design.attribute_axes`: optional multi-value cross-cutting tag/attribute axes.
- `feature_contract`: declares which derived axes are meant for retrieval, ranking, filtering, exclusion, or fallback. This lets recommendation logic consume the derived output without guessing column roles.
- `role`: optional axis role, usually `primary`, `secondary`, `attribute`, or `status`.
- `used_for_retrieval`: true when the axis can narrow the candidate pool.
- `used_for_ranking`: true when the axis can influence ordering or similarity.
- `used_for_filtering`: true when the axis can power search/filter UI or hard filters.
- `used_for_exclusion`: true when the axis can block unsafe or incompatible recommendations.
- `feature_weight_hint`: optional relative weight hint for downstream feature builders. It is guidance, not a model score.
- `multi_value`: if true, keep all matching values; otherwise pick the highest confidence match.
- `required`: if true, rows with no value for this axis become `needs_review`.
- `review_if_empty`: same review behavior as `required`; use when the axis is important but not always available during early rule development.
- `max_values`: optional cap for `multi_value` axes. Use this when a broad keyword could produce too many labels.
- `keywords`: case-insensitive substring matches after normalization.
- `negative_keywords`: if any match, this value rule is blocked.
- `regex`: regular expressions applied after normalization.
- `exact_values`: exact case-insensitive matches for one or more source columns. If a source cell is a JSON/list value, any item may match.
- `numeric_ranges`: numeric column thresholds with optional `min` and `max`.
- `all_of`: child criteria that must all match.
- `any_of`: child criteria where at least one must match.
- `none_of`: child criteria that must not match.
- `source_columns`: optional override. If absent, use top-level `text_columns`.
- `confidence`: base confidence for a match. Increase only when evidence is strong.
- `priority`: tie-breaker for non-multi axes. Higher priority wins when confidence is similar.
- `rule_id`: stable identifier for audit and future changes.
- `derived_output.identity_columns`: minimal identity/display source columns to keep when creating a rule-shaped derived output. Examples: `product_id`, `sku`, `goods_name`, `title`.
- `derived_output.drop_source_columns`: source classification columns replaced by derived axes and excluded from top-level derived output. This does not delete source data.
- `derived_output.audit_columns`: audit columns to keep directly in the derived table. Use `"minimal"` by default. Valid group names are `"none"`, `"minimal"`, `"standard"`, and `"full"`, or provide an explicit list of allowed audit columns.

## Output Value Policy

Axis values written into the final classified dataset should come from observed source labels whenever possible.

- Korean source data should output Korean values.
- English source data should output English values.
- Do not translate source labels into arbitrary English slugs.
- When aliases must be merged, choose a canonical value from an observed source label.
- `rule_id`, filenames, and internal metadata may use stable English/ASCII identifiers, but keep those separate from user-facing output values.

## Default Design Contract

For search, recommendation, cleanup, analytics, or derived table output, use this structure first unless the user explicitly asks for another shape:

- One representative primary axis: single-value, required or `review_if_empty`.
- Optional secondary axes: single-value, narrower subtype fields.
- Optional attribute axes: multi-value tags for cross-cutting meanings such as audience, function, lifecycle, material, risk, channel, collection, or status.

Do not model the main category as a broad multi-value axis. If one source field contains several meanings, split them across the primary axis, secondary axes, and attribute axes.

`scripts/create_derived_table.py` validates this contract when `taxonomy_design.strategy` is `representative_plus_attributes`.

Criteria groups are intentionally conservative:

- If `keywords` is present, at least one keyword must match.
- If `regex` is present, at least one regex must match.
- If `exact_values` is present, all listed columns must match.
- If `numeric_ranges` is present, all listed ranges must match.
- If multiple groups are present on one value rule, they are combined as AND.

Use `any_of` when OR behavior is needed.

## Review Status

Suggested status values:

- `auto_accepted`: high-confidence, non-conflicting rule match.
- `needs_review`: no match, weak match, or conflicting match.
- `rejected`: reviewed and rejected.
- `approved`: human-approved.

## Conflict Rules

- If one non-multi axis has multiple matched values with similar confidence, mark `needs_review`.
- If a rule contradicts an existing high-quality source label, mark `needs_review`.
- If no rule matches, keep the axis empty and mark `needs_review`.
- If a `required` or `review_if_empty` axis is empty, mark `needs_review` and record the axis in `missing_required_axes`.
- If average confidence is below `auto_accept_threshold`, mark `needs_review`.

## Output Columns

Sidecar outputs include:

- `axis_values`
- `confidence`
- `evidence`
- `rule_ids`
- `review_status`
- `conflicts`
- `missing_required_axes`

Enriched outputs prefix those fields by default:

- `classified_axis_values`
- `classified_confidence`
- `classified_evidence`
- `classified_rule_ids`
- `classified_review_status`
- `classified_conflicts`
- `classified_missing_required_axes`
- `classified_<axis_name>`

Derived outputs are created by `scripts/create_derived_table.py` and should include:

- `source_row_id`
- minimal identity/display columns from `derived_output.identity_columns`
- one column per rule axis
- minimal operational audit columns by default: `taxonomy_version`, `confidence`, `review_status`, `classified_at`

Detailed audit outputs can be created separately and include:

- `source_row_id`
- `taxonomy_version`
- `axis_values`
- `confidence`
- `review_status`
- `conflicts`
- `missing_required_axes`
- `rule_ids`
- `evidence`
- `classified_at`
