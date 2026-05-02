"""XGBoost LTR ranker.

보고서 권장:
- objective=rank:ndcg (LambdaMART 계열)
- learning_rate=0.05, max_depth=6, n_estimators=300
학습 데이터 1000건+ 확보 후 실제 학습 실행 (Track 14B, 다음 세션).
"""
from __future__ import annotations
import numpy as np


class FashionRanker:
    def __init__(self) -> None:
        self.model = None

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        qid: np.ndarray,
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
        qid_val: np.ndarray | None = None,
    ) -> None:
        import xgboost as xgb  # lazy import

        self.model = xgb.XGBRanker(
            objective="rank:ndcg",
            learning_rate=0.05,
            max_depth=6,
            n_estimators=300,
            subsample=0.8,
            colsample_bytree=0.8,
            tree_method="hist",
        )
        fit_kwargs: dict = {"qid": qid}
        if X_val is not None and y_val is not None and qid_val is not None:
            fit_kwargs.update({
                "eval_set": [(X_val, y_val)],
                "eval_qid": [qid_val],
                "verbose": True,
            })
        self.model.fit(X, y, **fit_kwargs)

    def predict(self, X: np.ndarray) -> np.ndarray:
        assert self.model is not None, "모델 미학습. train() 또는 load() 먼저 호출."
        return self.model.predict(X)  # type: ignore[return-value]

    def save(self, path: str) -> None:
        assert self.model is not None
        self.model.save_model(path)

    def load(self, path: str) -> None:
        import xgboost as xgb  # lazy import

        self.model = xgb.XGBRanker()
        self.model.load_model(path)


_ranker_singleton: FashionRanker | None = None


def get_ranker(model_path: str = "artifacts/ranker_v1.json") -> FashionRanker | None:
    """싱글턴 로드. 파일 없으면 None 반환 (softScoreProducts fallback)."""
    global _ranker_singleton
    if _ranker_singleton is not None:
        return _ranker_singleton
    import os
    if not os.path.exists(model_path):
        return None
    try:
        r = FashionRanker()
        r.load(model_path)
        _ranker_singleton = r
        return r
    except Exception:
        return None
