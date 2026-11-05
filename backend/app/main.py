"""The API. Each function below handles one URL (an "endpoint")."""
import logging
import time
import uuid
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import config
from .auth import create_token, current_user, hash_password, require_approver, verify_password
from .db import Base, SessionLocal, engine, get_db
from .logging_setup import request_id_var, setup_logging
from .models import AccessRequest, AuditEvent, User
from .schemas import (
    AuditOut,
    Credentials,
    RequestCreate,
    RequestOut,
    Status,
    StatusUpdate,
    TokenOut,
    UserOut,
)

setup_logging(config.LOG_LEVEL)
log = logging.getLogger("access_tracker")

if config.SENTRY_DSN:
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=config.ENVIRONMENT,
        release=config.APP_VERSION,
        traces_sample_rate=1.0,  # fine for a demo; lower this under real traffic
        send_default_pii=False,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables if they don't exist yet (fine for a small app; real projects use migrations).
    Base.metadata.create_all(engine)
    _seed_admin()
    log.info("startup_complete", extra={"version": config.APP_VERSION, "environment": config.ENVIRONMENT,
                                         "allowed_origins": config.ALLOWED_ORIGINS})
    yield


def _seed_admin() -> None:
    if not config.ADMIN_PASSWORD:
        log.warning("ADMIN_PASSWORD not set; no approver account was created")
        return
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == config.ADMIN_USERNAME)) is None:
            db.add(User(username=config.ADMIN_USERNAME, password_hash=hash_password(config.ADMIN_PASSWORD),
                        role="approver"))
            db.commit()
            log.info("admin_user_created", extra={"username": config.ADMIN_USERNAME})


app = FastAPI(title="Access Tracker API", version=config.APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],  # lets the browser's JavaScript read the request ID
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """Runs around every request: gives it an ID, times it, and writes one JSON log line."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    token = request_id_var.set(request_id)
    sentry_sdk.set_tag("request_id", request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        sentry_sdk.capture_exception(exc)  # no-op if Sentry isn't configured
        log.exception("unhandled_error", extra={"method": request.method, "path": request.url.path})
        response = JSONResponse({"detail": "Internal server error", "request_id": request_id}, status_code=500)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    log.info("http_request", extra={
        "method": request.method,
        "path": request.url.path,
        "query": str(request.url.query) or None,
        "status": response.status_code,
        "duration_ms": duration_ms,
    })
    request_id_var.reset(token)
    return response


# ---------- Health & info ----------

@app.get("/")
def root():
    return {"service": "access-tracker-api", "version": config.APP_VERSION, "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    """Used by Render and the uptime monitor. Checks the app AND that the database answers."""
    start = time.perf_counter()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        log.error("health_db_failed", extra={"error": str(exc)})
        db_status = "error"
    body = {
        "status": "ok" if db_status == "ok" else "degraded",
        "db": db_status,
        "db_latency_ms": round((time.perf_counter() - start) * 1000, 1),
        "version": config.APP_VERSION,
    }
    return JSONResponse(body, status_code=200 if db_status == "ok" else 503)


# ---------- Auth ----------

@app.post("/auth/register", response_model=TokenOut, status_code=201)
def register(body: Credentials, db: Session = Depends(get_db)):
    user = User(username=body.username, password_hash=hash_password(body.password), role="requester")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Username already taken") from None
    log.info("user_registered", extra={"username": user.username})
    return TokenOut(access_token=create_token(user), username=user.username, role=user.role)


@app.post("/auth/login", response_model=TokenOut)
def login(body: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        log.warning("login_failed", extra={"username": body.username})
        raise HTTPException(401, "Wrong username or password")
    log.info("login_succeeded", extra={"username": user.username})
    return TokenOut(access_token=create_token(user), username=user.username, role=user.role)


@app.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


# ---------- Access requests ----------

@app.post("/requests", response_model=RequestOut, status_code=201)
def create_request(body: RequestCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    req = AccessRequest(requester=user.username, **body.model_dump())
    req.audit_events.append(AuditEvent(action="created", new_status="pending", actor=user.username))
    db.add(req)
    db.commit()  # request + its first audit row are saved together in one transaction
    log.info("access_request_created", extra={"access_request_id": req.id, "resource": req.resource,
                                              "access_level": req.access_level, "requester": req.requester})
    return req


@app.get("/requests", response_model=list[RequestOut])
def list_requests(
    status: Status | None = None,
    resource: str | None = None,
    q: str | None = Query(default=None, description="Search requester, resource or justification"),
    mine: bool = False,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = select(AccessRequest).order_by(AccessRequest.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(AccessRequest.status == status)
    if resource:
        stmt = stmt.where(AccessRequest.resource.ilike(f"%{resource}%"))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(AccessRequest.requester.ilike(like), AccessRequest.resource.ilike(like),
                              AccessRequest.justification.ilike(like)))
    if mine:
        stmt = stmt.where(AccessRequest.requester == user.username)
    return db.scalars(stmt).all()


def _get_or_404(db: Session, request_id: int) -> AccessRequest:
    req = db.get(AccessRequest, request_id)
    if req is None:
        raise HTTPException(404, f"Access request {request_id} not found")
    return req


@app.get("/requests/{request_id}", response_model=RequestOut)
def get_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _get_or_404(db, request_id)


@app.patch("/requests/{request_id}/status", response_model=RequestOut)
def update_status(request_id: int, body: StatusUpdate, db: Session = Depends(get_db),
                  approver: User = Depends(require_approver)):
    req = _get_or_404(db, request_id)
    if req.status == body.status:
        raise HTTPException(409, f"Request is already {body.status}")
    old = req.status
    req.status = body.status
    req.audit_events.append(AuditEvent(action="status_changed", old_status=old, new_status=body.status,
                                       actor=approver.username, note=body.note))
    db.commit()  # status change + audit row commit together, so history can't get out of sync
    log.info("access_request_status_changed", extra={"access_request_id": req.id, "old_status": old,
                                                     "new_status": body.status, "actor": approver.username})
    return req


@app.get("/requests/{request_id}/audit", response_model=list[AuditOut])
def get_audit(request_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _get_or_404(db, request_id).audit_events


# ---------- Debug (for the monitoring demo) ----------

if config.ENABLE_DEBUG_ROUTES:
    @app.get("/debug/error")
    def debug_error():
        """Deliberately crashes so you can show the error arriving in Sentry and the logs."""
        raise RuntimeError("Deliberate test error for the monitoring demo")
