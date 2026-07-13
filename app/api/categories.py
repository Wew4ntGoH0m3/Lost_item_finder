from flask import Blueprint

from ..models import ITEM_CATEGORY_LABELS, ItemCategory
from ..utils import success

bp = Blueprint("categories", __name__)


@bp.get("")
def list_categories():
    return success(
        {
            "items": [
                {"code": category.value, "label": ITEM_CATEGORY_LABELS[category]}
                for category in ItemCategory
            ]
        }
    )
