# Source-Grounded Classifier 고도화 계획

## 1. 목표

현재 스킬은 `원본 분류 컬럼이 뒤섞인 데이터`를 `설명 가능한 rule 기반 분류 결과`로 안전하게 재구성하는 데 강점이 있다.  
고도화의 목표는 이 스킬을 `추천 로직에 바로 연결할 수 있는 재분류 파이프라인`으로 확장하는 것이다.

핵심 목표는 아래 4가지다.

1. 추천에 필요한 축을 안정적으로 만들어낼 것
2. 원본 데이터 보존 원칙을 유지할 것
3. 룰 기반 분류의 설명 가능성과 재현성을 유지할 것
4. 운영 중 반복 개선이 가능한 구조로 바꿀 것

추가로 이번 고도화에서 반드시 못 박아야 할 원칙이 있다.

> 새로 만드는 테이블은 원본 테이블의 축소 복사본이 아니라, 원본 정보에서 필요한 것만 남기고 재분류 결과를 중심으로 다시 설계한 "파생 테이블"이어야 한다.

즉, 불필요한 원본 컬럼을 습관적으로 같이 들고 가면 안 된다.

## 1.1 표준 실행 순서

이 스킬의 추천용 재분류 흐름은 아래 3단계로 고정한다.

1. 원본 데이터를 검토하여 어떤 속성들이 있는지 파악한다.
2. 파악한 속성들을 LLM 추천에 쓰기 좋은 새 컬럼 구조로 재정의한다.
3. 새로 정의된 컬럼을 가진 테이블을 만들고, 원본 데이터의 값을 새 컬럼 구조에 맞게 채운다.

단, 3단계에서 새 테이블은 원본 전체를 복사하지 않는다. 제품명, 제품번호, 원본 row id처럼 추적과 표시를 위해 필요한 최소 정보만 원본에서 그대로 가져오고, 나머지는 새로 정의한 canonical 컬럼에 맞춰 재분류된 값으로 채운다.

이 흐름을 더 구체화하면 다음과 같다.

1. 원본 속성 파악
   - 컬럼 목록, 데이터 타입, null 비율, distinct 수, top values, 샘플 값을 확인한다.
   - 기존 `category`, `subcategory`, `tag`, `type`, `status`, `label` 계열 컬럼이 어떤 의미를 섞고 있는지 본다.
   - 제품명, 제품번호, 브랜드, 가격, 설명, 옵션, 대상, 용도처럼 추천에 쓸 수 있는 후보 속성을 찾는다.
2. 추천용 새 컬럼 정의
   - 후보군 제한용 primary 컬럼을 정의한다.
   - 세부 구분용 secondary 컬럼을 정의한다.
   - 유사도, 필터링, 랭킹, 제외 조건에 쓸 attribute/tag 컬럼을 정의한다.
   - 각 컬럼이 `single_value`인지 `multi_value`인지, 필수인지 optional인지 정한다.
3. 새 테이블 생성과 값 채우기
   - `source_row_id`, `product_id`, `product_name` 같은 필수 식별/표시 컬럼만 원본에서 유지한다.
   - 기존 분류 컬럼은 새 canonical 컬럼으로 대체되면 top-level 새 테이블에서 제외한다.
   - rule 또는 LLM 보조 설계 결과를 기준으로 각 row를 새 컬럼에 매핑한다.
   - confidence, review_status, rule_ids, evidence는 추천 테이블에 꼭 필요한 최소 수준만 넣거나 별도 audit 산출물로 분리한다.

## 2. 현재 상태 요약

현재 저장소는 이미 좋은 기본기를 갖고 있다.

- `SKILL.md`
  - source mutation 금지
  - profile -> axis design -> rules -> apply -> validate 흐름 명확
  - `representative_plus_attributes` 전략 정의
- `scripts/profile_dataset.py`
  - 컬럼 분포, null rate, top values, sample profiling 가능
- `scripts/apply_rules.py`
  - deterministic rule 적용 가능
  - `confidence`, `evidence`, `rule_ids`, `review_status` 생성
- `scripts/classify_dataset.py`
  - 원본 보존하면서 enriched output 생성
- `scripts/validate_classification.py`
  - fill rate, conflict, low-confidence, unmatched 검증 가능

즉, 지금은 `분류 설계 스킬`로는 충분히 탄탄하다.  
하지만 추천 로직 관점에서는 아직 `추천 친화형 taxonomy 설계`, `후속 랭킹 피처 생성`, `운영 피드백 루프`가 약하다.

## 3. 추천 로직 기준의 핵심 한계

### 3.1 분류 결과는 있지만 추천 피처 계약이 약함

현재 구조는 `primary axis + secondary axis + attribute axes`를 만들 수 있지만,
추천 시스템이 바로 쓰기 좋은 형태로 어떤 축이 반드시 필요하고 어떤 축이 optional인지에 대한 계약이 약하다.

예:

- 대표 카테고리
- 세부 카테고리
- 브랜드/제조사
- 사용 대상
- 상황/목적
- 가격대
- 취향/스타일
- 금기 속성
- 시즌성
- 호환성

이런 축은 추천에서는 매우 중요하지만 현재 스킬은 이를 `도메인별 추천 피처 세트`로 표준화하지 않는다.

### 3.2 axis discovery는 강하지만 ranking-friendly output이 부족함

현재 output은 분류 결과와 evidence 중심이다.  
추천에서는 아래 같은 추가 산출물이 필요하다.

- filter용 단일값 필드
- retrieval용 다중 태그 필드
- similarity 계산용 정규화 피처
- cold-start fallback용 대표 속성
- 후보군 제어용 exclusion/inclusion 속성

즉, `분류 결과`에서 끝나지 않고 `추천 파이프라인용 피처 레이어`까지 가야 한다.

### 3.2-1 derived table이 너무 많은 원본 컬럼을 가져갈 위험

실사용에서 가장 자주 생기는 문제는 이거다.

- 원본 컬럼을 거의 그대로 복사함
- 새로 만든 axis와 의미가 겹치는 컬럼도 같이 남김
- 추천에 필요 없는 운영/수집/임시 컬럼까지 포함함
- 결국 새 테이블이 "재분류 결과물"이 아니라 "원본 덤프 + 분류 컬럼 몇 개 추가" 형태가 됨

이 상태는 추천 로직에 불리하다.

- 어떤 컬럼이 진짜 canonical field인지 불명확해짐
- downstream 쿼리와 feature builder가 불필요하게 복잡해짐
- 원본과 파생 의미가 섞여 데이터 계약이 흐려짐
- 컬럼이 많을수록 운영 중 잘못된 필드를 참조할 가능성이 커짐

따라서 derived table 생성 단계에서부터 `남길 컬럼`, `버릴 컬럼`, `축으로 대체된 컬럼`을 명시적으로 구분해야 한다.

### 3.3 confidence가 운영 의사결정에 충분히 세분화되어 있지 않음

현재 `confidence`는 평균 기반 단일 수치다.  
추천 로직에는 다음처럼 더 세분화된 신뢰도 정보가 필요하다.

- axis별 confidence
- 핵심 axis 미충족 여부
- source label 일치/불일치 여부
- 규칙 충돌 종류
- low-signal row 여부

이 정보가 있어야 추천에서
`완전 사용`, `부분 사용`, `후보군만 제한`, `검수 대기 제외`
같은 운영 정책을 세울 수 있다.

### 3.4 룰 생성과 개선 루프가 반자동 수준에 머물러 있음

현재는 사람이 설계하고 agent가 실행하는 구조다.  
추천 품질을 높이려면 아래 루프가 필요하다.

1. 분류 결과 생성
2. 추천 지표 악화 구간 확인
3. 어떤 axis/rule이 문제인지 역추적
4. 룰 보강안 생성
5. 재검증

즉, `rule authoring`을 넘어서 `rule evolution loop`가 필요하다.

## 4. 고도화 방향

## 4.1 1단계: 추천 목적 중심 Input Contract 확장

`SKILL.md`의 입력 계약에 추천 목적 필드를 더 명확히 넣는 것이 우선이다.

추가 권장 필드:

- `recommendation_mode`
  - `related_items`
  - `similar_items`
  - `bundle_cross_sell`
  - `personalized_ranking`
  - `search_filtering`
- `entity_type`
  - `product`, `content`, `document`, `ticket`, `listing` 등
- `must_have_axes`
  - 추천에 반드시 필요한 축
- `feature_priority`
  - `retrieval_first`, `ranking_first`, `filtering_first`
- `fallback_policy`
  - low-confidence row 처리 정책

이 단계의 목적은 스킬이 처음부터 `그냥 분류`가 아니라 `추천용 재분류`를 하도록 만드는 것이다.

## 4.2 2단계: 추천 친화형 Taxonomy Design Contract 추가

현재의 `representative_plus_attributes` 전략은 유지하되, 추천용 표준 역할을 추가한다.

권장 axis role:

- `primary`
  - 대표 분류. 후보군 1차 제한
- `secondary`
  - 세부 분류. 근접성 계산 보조
- `attribute`
  - 다중 태그. 유사도 계산용
- `facet`
  - 필터 UI/검색용
- `exclusion`
  - 같이 추천하면 안 되는 속성
- `compatibility`
  - 함께 추천 가능한 관계 속성
- `ranking_hint`
  - 선호도/품질/강도 같은 랭킹 보조 신호

추가로 각 axis마다 아래 메타데이터를 넣는 구조를 권장한다.

- `used_for_retrieval`
- `used_for_ranking`
- `used_for_filtering`
- `used_for_exclusion`
- `feature_weight_hint`

이렇게 해야 downstream 추천 로직이 분류 결과를 해석하지 않고 바로 사용할 수 있다.

## 4.3 3단계: Rule Schema를 추천 피처 스키마로 확장

`references/rule_schema.md`와 템플릿을 아래 방향으로 확장하는 것이 좋다.

추가 권장 필드:

```json
{
  "feature_contract": {
    "retrieval_axes": ["primary_category", "secondary_category"],
    "ranking_axes": ["benefit_tags", "audience_tags"],
    "filter_axes": ["life_stage", "price_band"],
    "exclusion_axes": ["allergy_tags"],
    "fallback_axes": ["primary_category"]
  }
}
```

또는 axis 단위 메타데이터:

```json
{
  "axes": {
    "primary_category": {
      "role": "primary",
      "used_for_retrieval": true,
      "used_for_ranking": true,
      "used_for_filtering": true
    }
  }
}
```

이 단계가 되면 결과물은 단순한 taxonomy JSON이 아니라
`추천 시스템이 바로 읽을 수 있는 feature contract`가 된다.

## 4.4 4단계: Output Shape를 추천 파이프라인 기준으로 분리

현재 output은 classification audit 중심이다.  
여기에 추천용 output을 명시적으로 분리하는 것이 필요하다.

권장 산출물:

1. `classified_output`
   - 현재처럼 audit/evidence 중심
2. `derived_output`
   - 사용자/분석가용 정제 결과
3. `recommendation_features`
   - 추천 엔진 입력용 얇은 테이블

예시 컬럼:

- `source_row_id`
- `primary_category`
- `secondary_category`
- `attribute_tags`
- `ranking_tags`
- `filter_tags`
- `exclusion_tags`
- `compatibility_tags`
- `confidence_overall`
- `confidence_core_axes`
- `review_status`
- `feature_ready`

특히 `feature_ready` 같은 운영 컬럼이 중요하다.

- `true`: 추천에 바로 사용 가능
- `partial`: 일부 축만 사용 가능
- `false`: 검수 전까지 추천 제외

여기서 더 중요한 출력 원칙은 아래다.

### 새 테이블 컬럼 구성 원칙

새 테이블에는 기본적으로 아래 3종류만 남긴다.

1. 최소 식별 컬럼
2. 최소 표시 컬럼
3. 재분류로 생성된 canonical 컬럼

예:

- 유지
  - `source_row_id`
  - `goods_name` 또는 `title`
  - `primary_category`
  - `secondary_category`
  - `benefit_tags`
  - `audience_tags`
  - `review_status`
  - `confidence`
- 제거 또는 top-level 제외
  - 기존 `category`, `subcategory`, `tag`, `type`
  - 추천에 직접 쓰지 않는 수집용 메타 컬럼
  - 사람이 읽기 어려운 중복 텍스트 컬럼
  - 재분류 후 역할이 끝난 중간 계산 컬럼

즉, 새 테이블은 아래 원칙을 따라야 한다.

- 원본 분류 컬럼을 그대로 복사하지 않는다.
- 새 canonical axis로 대체된 원본 컬럼은 top-level에서 제거한다.
- 설명용 원본 필드는 최소한만 남긴다.
- 감사용 정보는 별도 audit 컬럼으로 제한한다.
- "혹시 필요할지도 몰라서" 식의 컬럼 보존은 금지한다.

추천 기준으로 보면 `wide raw copy`보다 `thin canonical table`이 맞다.

### 권장 컬럼 선정 규칙

컬럼은 아래 기준으로 남긴다.

- 반드시 남김
  - 원본 row를 다시 찾기 위한 키
  - 화면 표시나 운영 확인에 필요한 대표 이름
  - 추천/검색/필터링에 직접 쓰는 재분류 컬럼
- 조건부 유지
  - 법적/운영상 꼭 필요한 상태값
  - 사용자 노출용 대표 가격/브랜드처럼 실제 기능에서 참조하는 값
- 제거
  - 재분류된 의미와 겹치는 기존 category 계열 컬럼
  - 비어 있거나 품질이 낮은 컬럼
  - 추천/검색/UI에서 소비하지 않는 내부 보조 컬럼
  - source text가 중복인 상세 설명 컬럼

이 기준을 `derived_output.identity_columns`와 `drop_source_columns` 계약으로 강제하는 방향이 맞다.

### 권장 산출물 분리

테이블을 두 층으로 나누는 것도 좋다.

1. `derived_classification_table`
   - 앱/추천이 직접 읽는 얇은 canonical 테이블
2. `classification_audit_table` 또는 파일
   - evidence, rule_ids, axis_values, review detail을 담는 감사용 산출물

이렇게 분리하면 추천 시스템은 필요한 필드만 읽고, 분석/검수는 audit 산출물을 별도로 볼 수 있다.

## 4.5 5단계: Validation을 추천 품질 관점으로 강화

현재 validation은 분류 검증에는 충분하다.  
추천 연계를 위해 아래 검증을 추가하는 것이 좋다.

추가 검증 항목:

- core axis fill rate
- retrieval axis coverage
- ranking axis sparsity
- exclusion axis precision 샘플 검토
- low-confidence row 비율
- source label 대비 drift
- rule collision 유형별 집계

권장 출력:

- `feature_readiness_report.json`
- `axis_coverage_report.json`
- `recommendation_risk_report.json`

핵심은 `분류가 되었는가`보다 `추천에 안전하게 써도 되는가`를 검증하는 것이다.

## 4.6 6단계: Human Review Queue를 운영 가능한 형태로 만들기

추천 시스템에서는 애매한 row를 억지로 분류하는 것이 더 위험하다.  
따라서 `needs_review`를 더 운영적으로 바꿔야 한다.

권장 세분화:

- `auto_accepted`
- `needs_review_missing_core_axis`
- `needs_review_conflict`
- `needs_review_low_signal`
- `needs_review_source_mismatch`

그리고 review queue에서 사람이 확인한 결과를 다시 룰 개선에 반영할 수 있어야 한다.

필요 기능:

- review 결과 export
- accepted/rejected 사유 저장
- rule candidate 생성용 피드백 샘플 추출

## 4.7 7단계: 반자동 Rule Improvement Loop 추가

고도화의 핵심은 여기다.  
추천에서 성능이 안 나오는 구간을 다시 룰 개선으로 연결해야 한다.

권장 루프:

1. 프로파일링
2. taxonomy 설계
3. initial rules 작성
4. classification 실행
5. validation 실행
6. review queue 분석
7. 룰 누락 패턴 추출
8. 후보 rule patch 생성
9. 재검증

이 단계에서 agent는 아래 역할을 수행할 수 있다.

- unmatched 상위 패턴 요약
- conflict 발생 row 공통 패턴 추출
- 빈도가 높은 신규 value 후보 탐지
- 기존 rule coverage gap 설명

즉, 스킬을 `one-shot classifier`에서 `iterative classifier optimizer`로 바꾸는 것이다.

## 4.8 8단계: LLM 보조 사용 지점을 더 정교하게 제한

현재 방향처럼 deterministic rule 우선 원칙은 유지하는 것이 맞다.  
다만 아래 지점에서는 LLM 보조를 선택적으로 넣는 것이 효율적이다.

- axis naming 후보 제안
- ambiguous sample clustering
- review queue에서 공통 패턴 요약
- 신규 rule 초안 생성

반대로 아래는 계속 rule-first가 맞다.

- 대량 자동 분류 실행
- 운영 배치 재처리
- 감사 가능한 최종 판정

정리하면 `LLM은 설계 보조`, `최종 실행은 deterministic`이 바람직하다.

## 5. 우선순위 로드맵

## Phase 1. 계약 강화

목표:
추천용 재분류라는 목적을 입력 계약과 출력 계약에 명시

작업:

- `SKILL.md`에 recommendation-specific input 추가
- `references/rule_schema.md`, `references/rule_schema.ko.md` 확장
- `templates/rules.template.json`에 feature contract 추가

완료 기준:

- 추천 목적이 명시된 요청에서 어떤 축이 필수인지 문서/스키마 차원에서 표현 가능

## Phase 2. 추천 피처 출력 추가

목표:
분류 결과를 추천 엔진이 바로 소비할 수 있는 형태로 분리

작업:

- `create_derived_table.py` 또는 신규 스크립트에서 recommendation feature output 지원
- `feature_ready`, `confidence_core_axes` 등 운영 컬럼 추가
- `drop_source_columns`를 실제 table contract 중심 옵션으로 강화
- 기본 동작을 "최소 identity + canonical 분류 컬럼만 유지"로 고정
- audit 정보는 필요 시 별도 output으로 분리

완료 기준:

- 추천 시스템이 audit JSON을 직접 해석하지 않고도 입력 테이블을 읽을 수 있음
- 새 테이블에 원본 분류 컬럼과 중복 컬럼이 남지 않음
- 컬럼 목록만 봐도 어떤 값이 canonical인지 명확함

## Phase 3. 검증 체계 고도화

목표:
분류 정확성뿐 아니라 추천 사용 가능성까지 검증

작업:

- `validate_classification.py` 확장
- core/retrieval/ranking axis coverage 추가
- risk report 추가

완료 기준:

- 결과물마다 “추천 투입 가능/보류”를 자동 판단할 수 있음

## Phase 4. 리뷰/개선 루프 추가

목표:
운영 데이터를 기반으로 룰을 계속 좋아지게 만들기

작업:

- review queue reason code 체계화
- unmatched/conflict 패턴 요약 리포트 추가
- rule patch suggestion 초안 생성

완료 기준:

- 룰 개선이 ad-hoc이 아니라 반복 가능한 운영 루프로 바뀜

## 6. 권장 구현 순서

실행 순서는 아래가 가장 안전하다.

1. 문서/스키마 계약부터 확장
2. 출력 스키마를 추천 친화형으로 추가
3. 검증 리포트를 추천 기준으로 강화
4. review queue 세분화
5. 반자동 rule 개선 루프 추가
6. 마지막으로 선택적 LLM 보조 연결

이 순서가 좋은 이유는,
먼저 계약과 출력이 안정되어야 나중에 자동화가 붙어도 구조가 흔들리지 않기 때문이다.

## 7. 바로 착수할 변경 후보

가장 먼저 손대기 좋은 파일은 아래다.

- `SKILL.md`
  - recommendation 목적 필드 추가
  - 추천 친화형 axis role 설명 추가
  - derived table은 최소 컬럼만 남긴다는 계약 명시
- `references/rule_schema.md`
  - feature contract / axis metadata 확장
  - `identity_columns`, `drop_source_columns`, `audit_columns` 계약 강화
- `references/rule_schema.ko.md`
  - 위 스키마 한국어 문서화
- `templates/rules.template.json`
  - 추천 피처 계약 예시 추가
- `scripts/create_derived_table.py`
  - audit 컬럼 분리 옵션
  - 불필요 원본 컬럼 제외 기본값 강화
- `scripts/validate_classification.py`
  - recommendation readiness 검증 추가

## 8. 성공 기준

고도화가 성공했다고 볼 기준은 아래다.

1. 같은 원본 데이터를 넣었을 때 추천용 피처가 일관되게 생성된다.
2. 핵심 분류 축의 coverage와 confidence를 분리해서 볼 수 있다.
3. 새 테이블에 불필요한 원본 컬럼이 남지 않는다.
4. 추천에 쓰면 안 되는 row를 자동으로 걸러낼 수 있다.
5. 사람이 검수한 결과가 다음 rule 개선으로 이어진다.
6. 추천 시스템이 분류 산출물을 별도 해석 없이 바로 소비할 수 있다.

## 9. 한 줄 결론

이 스킬의 다음 단계는 `분류 잘하는 스킬`이 아니라  
`추천 로직이 바로 사용할 수 있는 설명 가능한 feature-building skill`로 진화하는 것이다.
