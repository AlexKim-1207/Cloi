"""FashionCLIP LoRA 미세조정 (PEFT 라이브러리).
실행 조건: GCP T4 GPU 인스턴스에서 수동 실행.
배치당 ~30분, 데이터 5,000 pair 기준.
"""
# 스캐폴딩만 — 실제 구현은 데이터 1,000건 쌓인 후


def train_lora(
    pairs_jsonl: str,
    base_model: str = "patrickjohncyh/fashion-clip",
    output_dir: str = "training/checkpoints/lora_v1",
    rank: int = 8,
    epochs: int = 3,
    batch_size: int = 32,
):
    """LoRA fine-tuning 메인 함수.

    Args:
        pairs_jsonl: triplet 학습 데이터
        base_model: pretrained FashionCLIP
        output_dir: LoRA weight 저장 경로
        rank: LoRA rank (낮을수록 빠름, 8~16 권장)
        epochs: 학습 에포크
        batch_size: GPU 메모리 따라 조정
    """
    raise NotImplementedError("데이터 축적 대기 중. 1,000+ pair 시점에 구현.")


if __name__ == "__main__":
    train_lora('training/data/pairs/triplets.jsonl')
