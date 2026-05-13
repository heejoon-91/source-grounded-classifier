# Dataset Taxonomy Designer

한국어 | [English](README.md)

Dataset Taxonomy Designer는 데이터 안에 있는 기존 `category`, `tag`, `type`, `status`, `label` 같은 분류 컬럼을 분석해서, 더 쓸모 있는 분류 구조로 재설계하고 rule 기반으로 안전하게 분류 결과를 만들어주는 Codex skill입니다.

핵심 목적은 간단합니다.

> 원본 데이터는 건드리지 않고, 데이터의 실제 내용을 보고 더 좋은 분류 컬럼과 rule을 설계한 뒤, 분류 결과를 별도 파일이나 staging 테이블로 반환합니다.

상품 데이터 전용 skill은 아닙니다. 고객 문의, 문서, 주문, 리뷰, 콘텐츠, 장비, 로그 데이터처럼 기존 분류 컬럼이 애매하거나 여러 의미를 섞고 있는 데이터에 사용할 수 있습니다.

이 skill은 사용자가 여러 정제 단계를 직접 실행하도록 만드는 도구가 아닙니다. Agent가 내부적으로 데이터 프로파일링, 축 설계, rule 작성, rule 적용, 검증을 한 번에 처리하고, 사용자에게는 최종 분류 데이터와 짧은 결과 리포트를 반환하는 방식으로 사용합니다.

추천용 재분류의 표준 흐름은 아래와 같습니다.

```text
1. 원본 데이터를 검토해서 어떤 속성들이 있는지 파악합니다.
2. 그 속성들을 LLM 추천에 쓰기 좋은 새 컬럼 구조로 재정의합니다.
3. 새 컬럼을 가진 테이블을 만들고, 제품번호/제품명 같은 필수 식별/표시 정보만 원본에서 유지합니다.
```

새 테이블은 원본 전체 복사본이 아니라, 추천 로직이 바로 읽을 수 있는 얇은 canonical derived table이어야 합니다.

## 언제 사용하나요?

다음 상황에서 사용합니다.

- 기존 `category` / `subcategory`가 검색이나 추천에 잘 맞지 않을 때
- 하나의 컬럼에 상품군, 생애주기, 기능, 상태, 형태 같은 의미가 섞여 있을 때
- 데이터마다 다른 도메인별 분류 체계가 필요할 때
- 모델 학습 없이 설명 가능한 rule 기반 분류를 먼저 만들고 싶을 때
- 원본 DB나 원본 파일을 직접 수정하지 않고 staging 결과만 만들고 싶을 때
- 자동 분류와 사람이 검수해야 할 항목을 분리하고 싶을 때

## 예시

기존 상품 데이터가 이렇게 되어 있다고 가정합니다.

```text
pet_type    = ["강아지"]
category    = ["사료", "습식관"]
subcategory = ["전연령", "주식캔"]
```

기존 컬럼에는 여러 의미가 섞여 있습니다.

- `강아지`: 대상 동물
- `사료`: 상품군
- `습식관`: 전시/기획/컬렉션 성격
- `전연령`: 생애주기
- `주식캔`: 제품 형태

이 skill은 이런 의미를 분리해서 파생 분류 결과를 만들도록 agent를 안내합니다.

```json
{
  "species": ["강아지"],
  "primary_category": "사료",
  "life_stage": ["전연령"],
  "food_form": ["주식캔"],
  "display_collection": ["wet_food_zone"]
}
```

실제 컬럼 이름과 개수는 고정되어 있지 않습니다. Agent가 데이터의 컬럼, 값 분포, null 비율, 샘플, 사용 목적을 보고 필요한 축을 설계합니다.

## 기본 분류 설계 방식

이 skill의 기본 설계는 넓은 multi-value 카테고리 하나로 끝내지 않는 것입니다. 검색, 추천, 정제, 분석, derived table 목적이면 처음부터 아래 형태로 한 번에 분류하도록 설계합니다.

```text
대표 primary 축 1개       단일값, required 또는 review_if_empty
optional secondary 축     단일값, 더 좁은 세부 타입
optional attribute 축     다중값, 기능/대상/상태/형태/소재/위험/컬렉션 같은 교차 속성
```

상품 데이터라면 `primary_category`는 하나만 선택하고, 생애주기/건강기능/품절상태/형태 같은 의미는 별도 attribute 축으로 둡니다. 다른 도메인에서는 같은 원칙을 적용하되 이름만 바뀝니다. 예를 들어 고객 문의는 `primary_issue_type`, 문서는 `primary_content_type`, 장비 로그는 `primary_event_type`처럼 설계합니다.

이 계약은 rule 파일의 `taxonomy_design.strategy = representative_plus_attributes`로 표현되고, derived output 생성 시 스크립트가 구조를 검증합니다.

## Output 값 원칙

최종 데이터에 들어가는 분류 값은 원본 데이터에서 관측된 표현을 우선 사용합니다.

```text
좋음: primary_category = 사료
피함: primary_category = food
```

영어 slug는 `rule_id`, 파일명, 내부 metadata처럼 기술적인 식별자에만 사용합니다. 사용자나 DB에서 직접 보는 derived output 값은 원본 데이터의 언어와 controlled vocabulary를 보존합니다.

## 이 Skill이 내부적으로 하는 일

1. 데이터 구조를 확인합니다.
   - ID 컬럼
   - 제목/설명/본문 컬럼
   - 기존 category/tag/status/label 후보 컬럼
   - null이 많은 컬럼
   - multi-value 컬럼
   - 의미가 섞인 컬럼

2. 기존 분류의 문제를 찾습니다.
   - 같은 의미가 여러 이름으로 들어간 경우
   - 하나의 컬럼에 여러 의미 축이 섞인 경우
   - 너무 넓어서 검색/추천에 도움이 안 되는 분류
   - sparse하거나 신뢰하기 어려운 태그

3. 새 분류 축을 설계합니다.
   - 필수로 채워야 하는 core taxonomy column
   - 비어 있어도 되는 optional attribute/tag column
   - 단일값이어야 하는 축
   - 여러 값을 가질 수 있는 축
   - 값이 없으면 검수로 보내야 하는 축

4. rule을 만듭니다.
   - exact value
   - keyword
   - regex
   - numeric range
   - `all_of`, `any_of`, `none_of`
   - confidence
   - review behavior

5. 원본을 바꾸지 않고 결과를 만듭니다.
   - sidecar CSV
   - enriched copy
   - validation report
   - DB staging table
   - rule-defined derived table

## 사용 방법

사용자는 자연어로 요청하면 됩니다.

```text
이 CSV 데이터 분류 구조 분석해줘
```

```text
이 DB 테이블의 category/subcategory를 더 좋은 컬럼 구조로 재정의해줘
```

```text
원본은 건드리지 말고 분류 결과만 staging 테이블로 만들어줘
```

```text
goods_name만 남기고 rule로 만든 새 분류 컬럼 형태의 테이블로 만들어줘
```

```text
애매한 건 자동 분류하지 말고 needs_review로 빼줘
```

Agent는 요청을 받으면 `SKILL.md`의 workflow를 내부적으로 끝까지 수행합니다. 사용자가 아래 단계를 하나씩 실행할 필요는 없습니다.

```text
1. 데이터 프로파일링
2. 기존 분류 문제 진단
3. 새 분류 축 설계
4. rule 작성
5. 분류 결과 생성
6. 검증 리포트 생성
7. 최종 derived file/table과 짧은 리포트 반환
```

더 많은 예시는 [한글 사용자 명령 예시](references/commands.ko.md)를 참고하세요.

## 지원 입력

이 skill은 다음 형태의 데이터를 다루도록 설계되어 있습니다.

```text
csv
json
jsonl
postgres_table
postgres_dump
sqlite
```

DB dump는 운영 DB나 원본 DB에 바로 복원하지 않고, 임시 DB/schema에 복원해서 확인하는 흐름을 사용합니다.

## 출력 형태

일반적으로 다음과 같은 산출물을 만듭니다. 사용자가 받는 핵심 결과물은 `derived_output` 또는 DB derived/staging table이고, rule/schema/report 파일은 재현성과 검증을 위한 보조 산출물입니다.

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

결과 리포트에는 각 생성 컬럼의 생성 이유가 포함되어야 합니다.

```text
컬럼명
- 왜 만들었는지
- 어떤 원본 컬럼/값 분포/샘플이 근거였는지
- 단일값인지 다중값인지
- 값이 비거나 애매할 때 어떻게 처리하는지
```

DB 기반 작업에서는 staging table을 선호합니다.

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

주요 필드 의미는 다음과 같습니다.

| 필드 | 의미 |
|---|---|
| `axis_values` | 실제 사용할 정리된 분류 결과입니다. |
| `evidence` | 왜 그렇게 분류했는지에 대한 rule 근거입니다. |
| `confidence` | rule 기반 신뢰도입니다. |
| `rule_ids` | 매칭된 rule 식별자입니다. |
| `review_status` | `auto_accepted` 또는 `needs_review` 같은 검수 상태입니다. |
| `missing_required_axes` | 필수 분류 축인데 값을 채우지 못한 축 목록입니다. |

사용자가 “rule이 적용된 새 스키마 형태로 데이터를 달라”고 요청하면 derived output을 만듭니다. 이 경우 원본 컬럼을 그대로 다 복사하지 않고, 최소 식별/표시 컬럼과 rule로 생성된 컬럼만 남깁니다.

```text
derived_classification_table
- source_row_id
- product_id, sku, goods_name, title 같은 최소 식별/표시 원본 컬럼
- rule axis를 펼친 컬럼들
- taxonomy_version
- confidence
- review_status
- classified_at
```

상세 근거는 별도 audit 산출물로 분리할 수 있습니다.

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

예를 들어 상품 데이터라면 `pet_type`, `category`, `subcategory`, `health_concern_tags`처럼 새 분류 컬럼과 의미가 겹치는 기존 컬럼은 top-level derived output에서 제외하고, 필요한 추적 정보는 `evidence`에 남깁니다.

## 안전 원칙

가장 중요한 원칙은 이것입니다.

> 원본 데이터를 직접 수정하지 않습니다.

이 skill은 다음 작업을 기본 흐름에서 하지 않습니다.

- 원본 CSV 덮어쓰기
- 원본 DB 테이블 `UPDATE`
- 원본 DB 테이블 `DELETE`
- 원본 DB 테이블 `TRUNCATE`
- 원본 schema 직접 변경

항상 먼저 별도 결과물을 만듭니다.

```text
원본 데이터 -> 분석 -> rule 적용 -> 별도 결과 파일/staging table
```

원본 반영이 필요하면 별도 단계에서 migration 또는 ETL 계획을 만들고 명시적인 승인을 받은 뒤 진행해야 합니다.

## 잘하는 일

- 섞여 있는 category/subcategory를 의미별 컬럼으로 나누기
- 검색/추천/분석에 더 좋은 분류 구조 설계하기
- 모델 없이 설명 가능한 rule 기반 분류 만들기
- 자동 분류와 검수 대상을 나누기
- 원본을 보존하면서 분류 실험하기
- rule, confidence, evidence를 남겨 추적 가능하게 만들기

## 조심해야 할 점

- 데이터에 근거가 없는 값을 정확히 추론할 수는 없습니다.
- rule 기반이라 애매한 의미 추론에는 한계가 있습니다.
- taxonomy/schema `version`은 사용자가 거쳐야 하는 단계가 아니라, 같은 데이터셋의 rule과 결과를 추적하기 위한 내부 버전입니다.
- 이미지, 긴 설명, 리뷰 의미 분석처럼 복잡한 판단은 LLM, embedding, ML classifier가 추가로 필요할 수 있습니다.
- `auto_accepted`는 사람이 검토하지 않아도 된다는 절대적 보증이 아니라, 현재 rule 기준으로 충돌이나 필수값 누락이 없다는 뜻입니다.

## 주요 파일

| 파일 | 역할 |
|---|---|
| `SKILL.md` | Codex가 skill 사용 시 읽는 런타임 지침입니다. |
| `references/rule_schema.md` | 영어 rule schema 문서입니다. |
| `references/rule_schema.ko.md` | 한글 rule schema 문서입니다. |
| `references/commands.md` | 영어 사용자 명령 예시입니다. |
| `references/commands.ko.md` | 한글 사용자 명령 예시입니다. |
| `templates/rules.template.json` | 프로젝트별 분류 rule 작성을 시작하는 템플릿입니다. |
| `scripts/profile_dataset.py` | 데이터를 안전하게 프로파일링합니다. |
| `scripts/apply_rules.py` | sidecar 분류 결과를 생성합니다. |
| `scripts/classify_dataset.py` | enriched copy를 생성합니다. |
| `scripts/validate_classification.py` | 분류 결과를 검증합니다. |
| `scripts/create_staging_table.py` | 분류 결과를 staging 테이블에 적재합니다. |
| `scripts/create_derived_table.py` | rule axis를 실제 컬럼으로 펼친 derived CSV/JSON/DB 테이블을 생성합니다. |

## Rule 형식

Rule 작성 방식은 [한글 rule schema](references/rule_schema.ko.md)를 참고하세요. 영어 문서는 [rule_schema.md](references/rule_schema.md)에 있습니다.

## 한 줄 요약

이 skill은 agent가 아무 데이터나 보고 무작정 카테고리를 찍게 하는 도구가 아니라, 데이터의 구조와 근거를 보고 어떤 분류 컬럼이 필요하고 어떤 rule로 안전하게 분류할지 설계하고 실행하게 만드는 분류 설계 skill입니다.
