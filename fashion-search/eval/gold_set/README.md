# Gold Set 600 queries

## 구성
| 유형 | 수량 | 설명 |
|------|------|------|
| single_top | 200 | 셀럽 단일 상의 스크린샷 |
| layered_multi | 150 | 레이어드 다중 아이템 |
| outer_fit | 150 | 아우터/기장/핏 중요 |
| accessory | 100 | 가방/신발/액세서리 |

## 라벨 기준
- **2점**: same SKU (동일 상품, 동일 모델코드)
- **1점**: same design / acceptable substitute (유사 상품, 허용 가능한 대체품)
- **0점**: wrong (카테고리/색상/핏 불일치)

## 디렉토리 구조
```
gold_set/
  queries/         # 600 .jpg 이미지
  labels.jsonl     # {"query_id": "q001", "candidates": [{"product_id": "...", "label": 0|1|2}]}
  splits/
    train.txt      # train query_id 목록
    valid.txt      # validation query_id 목록
    test.txt       # test query_id 목록 (비공개)
```

## labels.jsonl 형식
```jsonl
{"query_id": "q001", "query_type": "single_top", "candidates": [{"product_id": "P123", "label": 2}, {"product_id": "P456", "label": 1}]}
```

## 라벨링 가이드
1. API `/api/analyze` 호출 → top-20 결과 수집
2. 각 결과 이미지와 query 이미지 비교
3. same SKU: 모델코드/브랜드 일치 + 색상/핏 동일 → 2점
4. same design: 같은 디자인이나 판매처 다름 + 색상/사이즈 허용 범위 → 1점
5. wrong: 카테고리 오류, 색상 완전 불일치, 기장 오류 → 0점
