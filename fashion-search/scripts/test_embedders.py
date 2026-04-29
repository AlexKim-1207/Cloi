"""Unit test: 3-embedder L2-norm and dimension check.

Run: python -m scripts.test_embedders
"""
import sys
import numpy as np
from PIL import Image

EMBEDDERS = [
    ("openclip_vitl14", 768),
    ("fashion_clip", 512),
    ("marqo_fashion_siglip", 768),
]

NORM_TOL = 1e-5


def make_dummy_image() -> Image.Image:
    arr = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
    return Image.fromarray(arr)


def test_embedder(name: str, expected_dim: int) -> bool:
    print(f"\n[{name}] loading...", flush=True)
    try:
        from src.embedding import get_embedder
        emb = get_embedder(name)
        emb.load()
        img = make_dummy_image()
        vec = emb.embed_single(img)

        if vec.shape != (expected_dim,):
            print(f"  FAIL dim: expected ({expected_dim},) got {vec.shape}")
            return False

        norm = float(np.linalg.norm(vec))
        if abs(norm - 1.0) > NORM_TOL:
            print(f"  FAIL norm: expected ~1.0, got {norm:.6f}")
            return False

        print(f"  PASS dim={vec.shape[0]} norm={norm:.6f}")
        return True

    except Exception as e:
        print(f"  FAIL exception: {e}")
        return False


def main():
    results = {}
    for name, dim in EMBEDDERS:
        results[name] = test_embedder(name, dim)

    print("\n" + "=" * 40)
    all_pass = True
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {status}  {name}")
        if not ok:
            all_pass = False

    if all_pass:
        print("\nAll embedders PASS")
        sys.exit(0)
    else:
        print("\nSome embedders FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
