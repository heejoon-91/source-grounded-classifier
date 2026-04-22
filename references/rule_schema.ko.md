# Rule Schema

한국어 | [English](rule_schema.md)

Rule은 프로젝트별로 달라집니다. Schema는 여러 도메인에서 재사용할 수 있도록 portable하고 명시적으로 유지합니다.

## 최소 JSON

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
  "derived_output": {
    "identity_columns": ["name"],
    "drop_source_columns": ["category", "subcategory"]
  },
  "axes": {
    "axis_name": {
      "description": "What this axis means",
      "role": "primary",
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

## 의미

- `axes`: 데이터에서 발견한 독립적인 의미 dimension입니다.
- `values`: 하나의 axis에서 허용되는 값입니다.
- `taxonomy_design.strategy`: 기본 one-pass 설계에는 `representative_plus_attributes`를 사용합니다. 대표 primary 축 1개와 optional secondary/attribute 축을 함께 만듭니다.
- `taxonomy_design.representative_axis`: 이 row가 주로 무엇인지 답하는 단일값 대표 축입니다.
- `taxonomy_design.secondary_axes`: optional 단일값 세부 타입 축입니다.
- `taxonomy_design.attribute_axes`: audience, function, lifecycle, material, risk, channel, collection, status처럼 교차적으로 붙는 optional multi-value 속성/tag 축입니다.
- `role`: optional axis 역할입니다. 보통 `primary`, `secondary`, `attribute`, `status`를 사용합니다.
- `multi_value`: true이면 매칭된 값을 모두 유지하고, false이면 confidence가 가장 높은 값을 선택합니다.
- `required`: true이면 이 axis에 값이 없는 row를 `needs_review`로 보냅니다.
- `review_if_empty`: `required`와 같은 review 동작입니다. 초기에 중요한 축이지만 항상 채워지지 않을 수 있을 때 사용합니다.
- `max_values`: `multi_value` axis에서 유지할 최대 값 개수입니다. 넓은 keyword가 너무 많은 label을 만들 때 사용합니다.
- `keywords`: 정규화 후 대소문자를 무시하는 substring match입니다.
- `negative_keywords`: 하나라도 매칭되면 해당 value rule은 차단됩니다.
- `regex`: 정규화 후 적용되는 regular expression입니다.
- `exact_values`: 하나 이상의 source column에 대한 대소문자 무시 exact match입니다. source cell이 JSON/list이면 항목 중 하나가 매칭될 수 있습니다.
- `numeric_ranges`: optional `min`, `max`를 가진 numeric column 조건입니다.
- `all_of`: 모든 child criteria가 매칭되어야 합니다.
- `any_of`: child criteria 중 하나 이상이 매칭되어야 합니다.
- `none_of`: child criteria가 매칭되지 않아야 합니다.
- `source_columns`: optional override입니다. 없으면 top-level `text_columns`를 사용합니다.
- `confidence`: match의 기본 confidence입니다. 증거가 강할 때만 높입니다.
- `priority`: non-multi axis에서 tie-breaker로 사용합니다. confidence가 비슷할 때 priority가 높은 값이 선택됩니다.
- `rule_id`: audit과 향후 변경 추적을 위한 안정적인 식별자입니다.
- `derived_output.identity_columns`: rule 적용 결과를 새 스키마 형태로 만들 때 유지할 최소 식별/표시 컬럼입니다. 예: `goods_name`, `title`.
- `derived_output.drop_source_columns`: 새 derived axis와 의미가 겹쳐 top-level derived output에서 제외할 원본 분류 컬럼입니다. 원본 자체를 삭제한다는 뜻은 아닙니다.

## Output Value 원칙

최종 classified dataset에 들어가는 axis value는 가능한 한 원본 데이터에서 관측된 분류명/태그명을 그대로 사용합니다.

- 한글 원본 데이터는 한글 값을 출력합니다.
- 영어 원본 데이터는 영어 값을 출력합니다.
- 임의로 영어 slug로 번역하지 않습니다.
- alias를 합쳐야 하면 원본에 실제 존재하는 대표 표현을 canonical value로 선택합니다.
- `rule_id`, 파일명, 내부 metadata는 안정성을 위해 영어/ASCII 식별자를 사용할 수 있지만, 사용자-facing output value와는 분리합니다.

## 기본 설계 계약

검색, 추천, 정제, 분석, derived table output 목적이면 사용자가 다른 형태를 명시하지 않는 한 아래 구조를 먼저 사용합니다.

- 대표 primary 축 1개: 단일값이고 `required` 또는 `review_if_empty`입니다.
- optional secondary 축: 단일값 세부 타입 필드입니다.
- optional attribute 축: audience, function, lifecycle, material, risk, channel, collection, status처럼 여러 값이 자연스러운 교차 속성/tag 필드입니다.

메인 카테고리를 넓은 multi-value 축 하나로 만들지 않습니다. 하나의 source field에 여러 의미가 섞여 있으면 primary 축, secondary 축, attribute 축으로 나눕니다.

`taxonomy_design.strategy`가 `representative_plus_attributes`이면 `scripts/create_derived_table.py`가 이 계약을 검증합니다.

Criteria group은 의도적으로 보수적으로 동작합니다.

- `keywords`가 있으면 keyword 중 하나 이상이 매칭되어야 합니다.
- `regex`가 있으면 regex 중 하나 이상이 매칭되어야 합니다.
- `exact_values`가 있으면 나열된 모든 column 조건이 매칭되어야 합니다.
- `numeric_ranges`가 있으면 나열된 모든 range 조건이 매칭되어야 합니다.
- 하나의 value rule 안에 여러 group이 있으면 AND로 결합됩니다.

OR 동작이 필요하면 `any_of`를 사용합니다.

## Review Status

권장 status 값:

- `auto_accepted`: high-confidence이고 conflict가 없는 rule match입니다.
- `needs_review`: match 없음, 약한 match, conflict가 있는 match입니다.
- `rejected`: 사람이 검토 후 거절한 상태입니다.
- `approved`: 사람이 승인한 상태입니다.

## Conflict Rules

- 하나의 non-multi axis에서 비슷한 confidence의 여러 value가 매칭되면 `needs_review`로 표시합니다.
- rule이 신뢰도 높은 기존 source label과 충돌하면 `needs_review`로 표시합니다.
- 어떤 rule도 매칭되지 않으면 axis를 비워 두고 `needs_review`로 표시합니다.
- `required` 또는 `review_if_empty` axis가 비어 있으면 `needs_review`로 표시하고 `missing_required_axes`에 기록합니다.
- 평균 confidence가 `auto_accept_threshold`보다 낮으면 `needs_review`로 표시합니다.

## Output Columns

Sidecar output에는 다음 컬럼을 포함합니다.

- `axis_values`
- `confidence`
- `evidence`
- `rule_ids`
- `review_status`
- `conflicts`
- `missing_required_axes`

Enriched output은 기본적으로 다음 prefix를 사용합니다.

- `classified_axis_values`
- `classified_confidence`
- `classified_evidence`
- `classified_rule_ids`
- `classified_review_status`
- `classified_conflicts`
- `classified_missing_required_axes`
- `classified_<axis_name>`

Derived output은 `scripts/create_derived_table.py`가 생성하며 다음 구조를 권장합니다.

- `source_row_id`
- `derived_output.identity_columns`에 지정된 최소 식별/표시 컬럼
- rule의 각 axis를 펼친 컬럼
- `taxonomy_version`
- `confidence`
- `review_status`
- `missing_required_axes`
- `rule_ids`
- `evidence`
- `classified_at`
