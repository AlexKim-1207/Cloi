"""평가 통과 시 LoRA 가중치 → Cloud Run 핫스왑."""


def deploy_new_model(
    lora_checkpoint_path: str,
    cloud_run_service: str = "fashion-search",
    region: str = "asia-northeast3",
) -> None:
    """evaluator.py 평가 통과 후 호출.

    새 모델 GCS 업로드 → Cloud Run 환경변수 업데이트 → 재배포.
    """
    raise NotImplementedError("데이터 축적 대기 중. evaluator 완성 후 구현.")
