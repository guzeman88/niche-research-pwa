"""Authenticated lightweight dashboard data; full evidence remains on its detail routes."""
from fastapi import APIRouter
from services.startup import summary

router = APIRouter(prefix='/api/startup', tags=['startup'])


@router.get('')
def overview():
    return summary()
