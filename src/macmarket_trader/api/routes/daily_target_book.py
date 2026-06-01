from __future__ import annotations

from fastapi import APIRouter, Depends

from macmarket_trader.api.deps.auth import require_approved_user
from macmarket_trader.daily_target_book.service import DailyTargetBookService


router = APIRouter(prefix="/user/daily-target-book", tags=["daily-target-book"])
daily_target_book_service = DailyTargetBookService()


@router.get("/latest")
def latest_daily_target_book(user=Depends(require_approved_user)):  # noqa: ARG001
    return daily_target_book_service.latest_template()


@router.post("/build")
def build_daily_target_book(req: dict[str, object] | None = None, user=Depends(require_approved_user)):
    return daily_target_book_service.build(user=user, request=req or {})
