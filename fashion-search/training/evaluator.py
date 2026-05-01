"""gold set 100개 회귀 테스트 — 새 모델 vs 현재 모델."""


def evaluate_model(
    model_path: str,
    gold_set_path: str = "training/gold_set/ground_truth.jsonl",
) -> dict:
    """Recall@5, Recall@10, MRR 계산.

    gold_set 형식 (각 라인):
        {
            "query_image_path": "training/gold_set/queries/001.jpg",
            "relevant_product_ids": ["pid_1", "pid_2"]
        }
    """
    raise NotImplementedError("Gold set 100개 수동 라벨링 필요.")
