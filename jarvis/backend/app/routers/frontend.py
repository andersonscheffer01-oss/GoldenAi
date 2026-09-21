from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import ROOT_DIR


router = APIRouter(tags=["frontend"])
FRONTEND_DIR = ROOT_DIR / "frontend"


def _file(name: str) -> FileResponse:
    path = (FRONTEND_DIR / name).resolve()
    if not str(path).startswith(str(FRONTEND_DIR.resolve())) or not path.exists():
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
    return FileResponse(path)


@router.get("/", include_in_schema=False)
def root():
    return _file("index.html")


@router.get("/app", include_in_schema=False)
def app_page():
    return _file("index.html")


@router.get("/login", include_in_schema=False)
def login_page():
    return _file("login.html")


@router.get("/manifest.json", include_in_schema=False)
def manifest():
    return _file("manifest.json")


@router.get("/sw.js", include_in_schema=False)
def service_worker():
    return _file("sw.js")
