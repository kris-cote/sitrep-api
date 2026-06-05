# app/api/routers/events.py
from typing import List
from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select

from app.models.db import get_session
from app.models.entities import Event
from app.models.schemas import EventCreate, EventRead
from app.core.security import verify_api_key

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: EventCreate,
    session: Session = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    event = Event(**payload.model_dump())
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.get("", response_model=List[EventRead])
def list_events(
    session: Session = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    events = session.exec(select(Event).order_by(Event.created_at.desc()).limit(100)).all()
    return events
