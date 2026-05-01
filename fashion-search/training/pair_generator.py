"""positive/negative pair 생성 + hard negative mining."""
import json
from pathlib import Path


def generate_pairs(
    sessions_jsonl: str,
    output_jsonl: str,
    hard_negative_top_k: int = 5,
) -> dict:
    """세션 jsonl → (query, positive, negative) triplet jsonl.

    각 라인: {"query": "image_hash", "positive": "product_id", "negative": "product_id"}
    """
    pairs = []
    with open(sessions_jsonl) as f:
        for line in f:
            sess = json.loads(line)
            for pos in sess['positives']:
                negs = sess['negatives'][:hard_negative_top_k]
                for neg in negs:
                    pairs.append({
                        'query': sess['image_hash'],
                        'positive': pos,
                        'negative': neg,
                    })

    Path(output_jsonl).parent.mkdir(parents=True, exist_ok=True)
    with open(output_jsonl, 'w') as f:
        for p in pairs:
            f.write(json.dumps(p) + '\n')

    return {'total_pairs': len(pairs)}


if __name__ == "__main__":
    stats = generate_pairs(
        'training/data/raw/sessions.jsonl',
        'training/data/pairs/triplets.jsonl',
    )
    print(f"Generated: {stats}")
