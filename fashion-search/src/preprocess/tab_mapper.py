"""detect label과 style_analyzer tab_id 간 매핑."""
from typing import Iterable, Optional


TAB_TO_LABELS_PRIORITY: dict[str, list[str]] = {
    'top_outer': ['top_outer', 'top'],
    'top_inner': ['top_inner', 'top'],
    'outer': ['outer', 'top_outer'],
    'bottom': ['bottom'],
    'dress': ['dress'],
    'shoes': ['shoes'],
    'bag': ['bag'],
    'accessory_ring': ['accessory_ring'],
    'accessory_necklace': ['accessory_necklace'],
    'accessory_earring': ['accessory_earring'],
    'accessory_belt': ['accessory_belt'],
    'accessory_hat': ['accessory_hat'],
    'accessory_watch': ['accessory_watch'],
}


def map_tab_to_label(tab_id: str, available_labels: Iterable[str]) -> Optional[str]:
    """탭 ID에 대응되는 detect 레이블을 우선순위 순으로 찾아 반환."""
    available = set(available_labels)
    priority = TAB_TO_LABELS_PRIORITY.get(tab_id, [])
    for label in priority:
        if label in available:
            return label
    return None
