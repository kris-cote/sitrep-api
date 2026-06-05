# app/api/routers/commands.py
from typing import List
from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select

from app.models.db import get_session
from app.models.entities import Command
from app.models.schemas import CommandCreate, CommandRead
from app.core.security import verify_api_key

router = APIRouter(prefix="/api/v1/commands", tags=["commands"])


@router.post("", response_model=CommandRead, status_code=status.HTTP_201_CREATED)
def create_command(
    payload: CommandCreate,
    session: Session = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    cmd = Command(**payload.model_dump())
    session.add(cmd)
    session.commit()
    session.refresh(cmd)
    return cmd


@router.get("", response_model=List[CommandRead])
def list_commands(
    session: Session = Depends(get_session),
    _: str = Depends(verify_api_key),
):
    cmds = session.exec(select(Command).order_by(Command.created_at.desc()).limit(100)).all()
    return cmds
