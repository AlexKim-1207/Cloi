"""3 임베딩 모델 비교: FashionCLIP vs OpenCLIP vs SigLIP2.

보고서 권장 메트릭: Recall@1/5/20, MRR
GPU 환경에서 실행 권장. CPU 가능하나 느림.
Usage: cd fashion-search && python eval/benchmark_models.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

GOLD_SET_FILE = Path(__file__).parent / "gold_set" / "labels.jsonl"
CATALOG_META = Path(__file__).parent.parent / "src" / "data" / "catalog" / "meta.json"
RESULTS_DIR = Path(__file__).parent / "results"


def load_gold(sample: int = 50) -> list[dict]:
    if not GOLD_SET_FILE.exists():
        print(f"SKIP: gold set 없음 ({GOLD_SET_FILE})")
        return []
    items = []
    with open(GOLD_SET_FILE) as f:
        for line in f:
            items.append(json.loads(line.strip()))
    return items[:sample]


def load_catalog_images() -> list[dict[str, Any]]:
    if not CATALOG_META.exists():
        return []
    meta = json.loads(CATALOG_META.read_text())
    catalog_dir = CATALOG_META.parent
    items = []
    for item in meta if isinstance(meta, list) else meta.get("items", []):
        img_path = catalog_dir / f"{item['id']}.jpg"
        if img_path.exists():
            items.append({**item, "img_path": str(img_path)})
    return items


class FashionCLIPEmbedder:
    def __init__(self) -> None:
        from transformers import CLIPModel, CLIPProcessor
        self.model = CLIPModel.from_pretrained("patrickjohncyh/fashion-clip")
        self.processor = CLIPProcessor.from_pretrained("patrickjohncyh/fashion-clip")

    def embed_images(self, paths: list[str]) -> np.ndarray:
        import torch
        from PIL import Image
        images = [Image.open(p).convert("RGB") for p in paths]
        inputs = self.processor(images=images, return_tensors="pt", padding=True)
        with torch.no_grad():
            embs = self.model.get_image_features(**inputs)
        embs = embs / embs.norm(dim=-1, keepdim=True)
        return embs.cpu().numpy()


class OpenCLIPEmbedder:
    def __init__(self) -> None:
        import open_clip
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            "ViT-B-16", pretrained="openai"
        )
        self.model.eval()

    def embed_images(self, paths: list[str]) -> np.ndarray:
        import torch
        from PIL import Image
        images = torch.stack([self.preprocess(Image.open(p).convert("RGB")) for p in paths])
        with torch.no_grad():
            embs = self.model.encode_image(images)
        embs = embs / embs.norm(dim=-1, keepdim=True)
        return embs.cpu().numpy()


class SigLIP2Embedder:
    def __init__(self) -> None:
        from transformers import AutoModel, AutoProcessor
        self.model = AutoModel.from_pretrained("google/siglip2-base-patch16-224")
        self.processor = AutoProcessor.from_pretrained("google/siglip2-base-patch16-224")

    def embed_images(self, paths: list[str]) -> np.ndarray:
        import torch
        from PIL import Image
        images = [Image.open(p).convert("RGB") for p in paths]
        inputs = self.processor(images=images, return_tensors="pt", padding=True)
        with torch.no_grad():
            embs = self.model.get_image_features(**inputs)
        embs = embs / embs.norm(dim=-1, keepdim=True)
        return embs.cpu().numpy()


MODELS = [
    ("fashion_clip", FashionCLIPEmbedder),
    ("openclip_vitb16", OpenCLIPEmbedder),
    ("siglip2_base", SigLIP2Embedder),
]


def recall_at_k(predicted_ids: list[str], gold: list[dict], k: int) -> float:
    relevant = {c["product_id"] for c in gold if c["label"] > 0}
    if not relevant:
        return 0.0
    return len(set(predicted_ids[:k]) & relevant) / len(relevant)


def mrr(predicted_ids: list[str], gold: list[dict]) -> float:
    relevant = {c["product_id"] for c in gold if c["label"] > 0}
    for i, pid in enumerate(predicted_ids):
        if pid in relevant:
            return 1.0 / (i + 1)
    return 0.0


def benchmark(embedder_cls: type, gold: list[dict], catalog: list[dict]) -> dict[str, float]:
    print(f"  Loading {embedder_cls.__name__}...")
    embedder = embedder_cls()

    catalog_paths = [c["img_path"] for c in catalog]
    catalog_ids = [str(c["id"]) for c in catalog]
    catalog_embs = embedder.embed_images(catalog_paths)

    metrics: dict[str, list[float]] = {"recall@1": [], "recall@5": [], "recall@20": [], "mrr": []}
    query_dir = GOLD_SET_FILE.parent / "queries"

    for q in gold:
        qid = q["query_id"]
        img_path = query_dir / f"{qid}.jpg"
        if not img_path.exists():
            continue
        q_emb = embedder.embed_images([str(img_path)])[0]
        sims = catalog_embs @ q_emb
        top_idx = np.argsort(-sims)[:20]
        predicted = [catalog_ids[i] for i in top_idx]
        candidates = q.get("candidates", [])
        metrics["recall@1"].append(recall_at_k(predicted, candidates, 1))
        metrics["recall@5"].append(recall_at_k(predicted, candidates, 5))
        metrics["recall@20"].append(recall_at_k(predicted, candidates, 20))
        metrics["mrr"].append(mrr(predicted, candidates))

    return {k: sum(v) / len(v) if v else 0.0 for k, v in metrics.items()}


def main() -> None:
    gold = load_gold(50)
    catalog = load_catalog_images()
    if not gold or not catalog:
        print("SKIP: gold set 또는 카탈로그 없음")
        sys.exit(0)

    results: dict[str, dict[str, float]] = {}
    for name, cls in MODELS:
        print(f"Benchmarking {name}...")
        try:
            results[name] = benchmark(cls, gold, catalog)
            print(f"  {name}: {results[name]}")
        except Exception as e:
            print(f"  {name} 실패: {e}", file=sys.stderr)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "model_benchmark.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n결과 저장: {out}")
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
