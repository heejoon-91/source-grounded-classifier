# 사용자 명령 예시

한국어 | [English](commands.md)

아래는 사용자가 이 skill을 사용하는 agent에게 줄 수 있는 자연어 명령 예시입니다. Shell 명령이 아닙니다. Agent는 요청을 해석하고, 제공된 데이터를 확인한 뒤 `SKILL.md`에 정의된 안전한 흐름을 선택해야 합니다.

## 탐색 / 프로파일링

| 사용자 명령 | Agent 행동 |
|---|---|
| `이 CSV 데이터 분류 구조 분석해줘` | CSV를 프로파일링하고 ID/text/category 후보 컬럼, null 비율, 상위 값, 과적재된 컬럼 가능성을 요약합니다. 사용자가 요청하지 않으면 분류 결과 파일은 만들지 않습니다. |
| `이 JSON 파일에서 카테고리로 쓸만한 컬럼 찾아줘` | JSON을 flatten/load하고, 필드를 프로파일링한 뒤 category-like 컬럼을 평가하고 어떤 컬럼이 신뢰 가능한지 설명합니다. |
| `이 DB 테이블 분류 가능한지 봐줘` | 테이블 스키마와 샘플 row를 확인하고 기존 label/tag/status 필드와 rule 기반 분류 가능성을 판단합니다. |
| `이 dump 파일에서 분류 대상 테이블 찾아줘` | dump를 임시 DB/schema에만 복원하고 테이블을 확인한 뒤 분류 대상 후보 테이블을 제안합니다. 운영 DB나 원본 데이터는 변경하지 않습니다. |

## 분류 축 설계

| 사용자 명령 | Agent 행동 |
|---|---|
| `이 데이터는 어떤 컬럼으로 세분화하면 좋을지 설계해줘` | 데이터 증거와 목적을 기준으로 의미 축을 찾고, 파생 분류 컬럼 또는 staging table schema를 제안합니다. |
| `검색에 쓰기 좋은 분류 체계로 다시 설계해줘` | 검색/필터링에 유리하도록 분류 축을 최적화하고, 섞여 있는 의미를 별도 dimension으로 분리합니다. |
| `추천에 쓰기 좋은 태그 구조로 설계해줘` | 추천 signal에 맞춰 대상, need-state, compatibility, function, risk, preference 같은 축을 데이터가 뒷받침하는 범위에서 식별합니다. |
| `처음부터 대표 카테고리 1개와 속성 태그로 나눠서 분류해줘` | `taxonomy_design.strategy=representative_plus_attributes`를 사용합니다. 대표 primary 축은 단일값/필수로 만들고, 보조 타입과 교차 속성은 별도 축으로 분리합니다. |
| `기존 category/subcategory가 괜찮은지 판단해줘` | 기존 category-like 필드를 샘플/상위 값과 비교해 의미 축 혼합, sparse tag, 명칭 불일치, 모호한 값을 찾습니다. |
| `왜 이런 컬럼을 만들었는지도 같이 설명해줘` | 최종 결과 리포트에 각 생성 컬럼의 목적, 원본 근거, 단일/다중값 정책, 검수 동작을 포함합니다. |

## Rule 작성

| 사용자 명령 | Agent 행동 |
|---|---|
| `이 기준으로 rules.json 만들어줘` | `templates/rules.template.json`과 `references/rule_schema.md`를 기준으로 프로젝트 전용 rule 파일을 만듭니다. 응답에는 데이터 근거를 포함해야 합니다. |
| `모델 없이 rule 기반으로 분류되게 만들어줘` | keyword/regex/exact/numeric 기반 deterministic rule을 작성하고 confidence/review 동작을 설명합니다. ML 모델은 도입하지 않습니다. |
| `애매한 건 검수 대상으로 빠지게 해줘` | 불확실한 row가 `needs_review`가 되도록 보수적인 confidence, conflict handling, `auto_accept_threshold`를 설정합니다. |
| `이 rule이 어떤 데이터를 잡는지 설명해줘` | 각 rule의 axis, value, match criteria, evidence columns, confidence, false-positive 위험을 설명합니다. |

## 분류 결과 생성

| 사용자 명령 | Agent 행동 |
|---|---|
| `원본에 분류 컬럼을 붙인 새 파일로 반환해줘` | `scripts/classify_dataset.py`를 실행하거나 제안합니다. 원본을 덮어쓰지 않고 `classified_*` 컬럼이 붙은 enriched copy를 만듭니다. |
| `분류 결과만 따로 파일로 만들어줘` | `scripts/apply_rules.py`를 실행하거나 제안합니다. row ID, axis values, confidence, evidence, rule IDs, review status가 포함된 sidecar CSV를 만듭니다. |
| `DB staging 테이블로 적재해줘` | sidecar output을 만든 뒤 `scripts/create_staging_table.py`로 staging table에 적재합니다. 원본 테이블은 update하지 않습니다. |
| `rule로 만든 새 스키마 형태의 테이블로 만들어줘` | `scripts/create_derived_table.py`를 실행하거나 제안합니다. 원본 분류 컬럼은 top-level에서 제외하고, 최소 식별 컬럼과 rule axis 컬럼, audit 컬럼으로 구성된 별도 derived table을 만듭니다. |
| `분류 설계부터 최종 데이터 생성까지 한번에 해줘` | 프로파일링, 축 설계, rule 작성, 분류 적용, 검증을 내부적으로 일괄 수행하고 최종 derived file/table과 짧은 리포트를 반환합니다. 사용자가 각 단계를 따로 실행하지 않게 합니다. |
| `대표 분류는 하나만 고르고 나머지는 태그 컬럼으로 만들어줘` | derived output 생성 전에 rule 파일의 대표축/보조축/속성축 계약을 검증하고, 위반하면 rule 설계부터 수정합니다. |
| `goods_name만 남기고 새 분류 컬럼 형태로 CSV 만들어줘` | 최소 표시 컬럼과 rule-defined columns만 포함하는 derived CSV를 만듭니다. 기존 `category/subcategory`처럼 새 컬럼과 중복되는 원본 분류 컬럼은 포함하지 않습니다. |
| `분류 결과 검증 리포트 만들어줘` | `scripts/validate_classification.py`를 실행하거나 제안하고 fill rate, rule counts, conflicts, review status, unmatched rows, low-confidence samples를 요약합니다. |
| `최종 결과랑 컬럼 생성 이유를 같이 줘` | 최종 derived file/table을 생성한 뒤, 각 derived column을 만든 이유와 근거를 짧은 리포트로 함께 반환합니다. |

## 반복 개선

| 사용자 명령 | Agent 행동 |
|---|---|
| `needs_review 나온 항목들 보고 rule 개선해줘` | low-confidence/unmatched/conflict sample을 확인하고 rule 변경을 제안한 뒤 새 output으로 재실행하고 검증 리포트를 비교합니다. |
| `오분류 가능성 높은 rule 찾아줘` | 넓은 keyword, 과도하게 많이 매칭되는 rule, conflict, 의심 sample을 검토하고 더 엄격한 조건이나 negative condition을 제안합니다. |
| `이전 버전과 결과 비교해줘` | 두 classification output을 row ID 기준으로 비교하고 axis values, review status, confidence, rule IDs 변경과 원인을 보고합니다. |
| `운영 반영 계획만 세워줘` | source data를 변경하지 않고 staged rollout/migration 계획만 작성합니다. backup, review, validation, rollback 단계를 포함합니다. |

## 안전 / 개인정보

| 사용자 명령 | Agent 행동 |
|---|---|
| `민감정보는 숨기고 프로파일링해줘` | redaction/no-sample 옵션을 사용하고 민감한 sample 값을 출력하지 않습니다. |
| `원본 파일은 절대 건드리지 말고 결과만 만들어줘` | output-only 동작을 강제합니다. in-place write를 거부하고 sidecar 또는 enriched copy를 생성합니다. |
| `DB 원본 테이블 업데이트하지 말고 staging만 만들어줘` | staging table만 만들거나 갱신합니다. `UPDATE`, `DELETE`, `TRUNCATE`, source table schema 변경은 하지 않습니다. |

## 최소 입력 템플릿

```markdown
데이터 분류를 해줘.

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

사용자가 파일이나 테이블만 제공한 경우에는 안전한 범위에서 추론하고, 진행을 막는 정보만 간결하게 질문합니다.
