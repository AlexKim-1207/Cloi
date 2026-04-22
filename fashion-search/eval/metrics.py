"""검색 품질 평가 지표.

지표:
    Recall@K  — 정답 상품이 상위 K개 결과에 포함되는 비율
    MRR       — Mean Reciprocal Rank (정답 첫 등장 순위 역수 평균)
    Category Precision@K — 상위 K개 중 올바른 카테고리 비율

Usage:
    from eval.metrics import evaluate
    results = evaluate(ground_truth, predictions)
"""
from dataclasses import dataclass


@dataclass
class EvalResult:
    recall_at_10: float
    recall_at_50: float
    mrr: float
    category_precision_at_10: float
    n_queries: int


def recall_at_k(
    relevant_ids: list[str],
    predicted_ids: list[str],
    k: int,
) -> float:
    """상위 k개 결과 중 정답이 하나라도 있는지 여부 (binary).

    Args:
        relevant_ids: 정답 product_id 리스트
        predicted_ids: 예측 결과 product_id 리스트 (score 내림차순)
        k: 상위 k개

    Returns:
        1.0 (정답 포함) 또는 0.0
    """
    relevant_set = set(relevant_ids)
    return 1.0 if any(p in relevant_set for p in predicted_ids[:k]) else 0.0


def reciprocal_rank(relevant_ids: list[str], predicted_ids: list[str]) -> float:
    """정답이 처음 등장하는 순위의 역수."""
    relevant_set = set(relevant_ids)
    for rank, pid in enumerate(predicted_ids, 1):
        if pid in relevant_set:
            return 1.0 / rank
    return 0.0


def category_precision_at_k(
    query_category: str,
    predicted_meta: list[dict],
    k: int,
) -> float:
    """상위 k개 결과 중 올바른 카테고리 비율."""
    if not predicted_meta:
        return 0.0
    top_k = predicted_meta[:k]
    matches = sum(1 for m in top_k if m.get("category", "") == query_category)
    return matches / len(top_k)


def evaluate(
    ground_truth: list[dict],
    predictions: list[list[dict]],
) -> EvalResult:
    """전체 쿼리 셋 평가.

    Args:
        ground_truth: 각 쿼리의 정답 정보
            [{"relevant_ids": [...], "category": "top"}, ...]
        predictions: 각 쿼리의 예측 결과
            [[{"product_id": "...", "category": "...", ...}, ...], ...]

    Returns:
        EvalResult
    """
    n = len(ground_truth)
    if n == 0:
        return EvalResult(0.0, 0.0, 0.0, 0.0, 0)

    r10_sum = r50_sum = mrr_sum = cp10_sum = 0.0

    for gt, preds in zip(ground_truth, predictions):
        relevant = gt.get("relevant_ids", [])
        category = gt.get("category", "")
        pred_ids = [p["product_id"] for p in preds]
        pred_meta = preds

        r10_sum += recall_at_k(relevant, pred_ids, 10)
        r50_sum += recall_at_k(relevant, pred_ids, 50)
        mrr_sum += reciprocal_rank(relevant, pred_ids)
        cp10_sum += category_precision_at_k(category, pred_meta, 10)

    return EvalResult(
        recall_at_10=round(r10_sum / n, 4),
        recall_at_50=round(r50_sum / n, 4),
        mrr=round(mrr_sum / n, 4),
        category_precision_at_10=round(cp10_sum / n, 4),
        n_queries=n,
    )
