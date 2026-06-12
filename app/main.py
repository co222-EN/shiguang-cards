from __future__ import annotations

from tempfile import TemporaryDirectory
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .ai import analyze_image, fallback_analysis
from .auth import COOKIE_NAME, create_session_token, require_session, verify_session_token
from .config import BASE_DIR, settings
from .images import make_images, restyle_card_for_analysis, validate_image
from .models import MomentRecord, RecordPatch, SessionRequest
from .storage import create_store


app = FastAPI(title=settings.app_name)
store = create_store()

static_dir = BASE_DIR / "static"
data_dir = settings.data_dir

data_dir.mkdir(parents=True, exist_ok=True)
(data_dir / "photos" / "original").mkdir(parents=True, exist_ok=True)
(data_dir / "photos" / "cropped").mkdir(parents=True, exist_ok=True)
(data_dir / "photos" / "thumbs").mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.mount("/data", StaticFiles(directory=data_dir), name="data")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(
        static_dir / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(
        static_dir / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/service-worker.js")
def service_worker() -> FileResponse:
    return FileResponse(
        static_dir / "service-worker.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/session")
def session_state(request: Request) -> dict[str, bool]:
    unlocked = True
    if settings.app_passcode:
        unlocked = verify_session_token(request.cookies.get(COOKIE_NAME))
    return {"passcode_required": bool(settings.app_passcode), "unlocked": unlocked}


@app.post("/api/session")
def create_session(payload: SessionRequest, response: Response) -> dict[str, bool]:
    if settings.app_passcode and payload.passcode != settings.app_passcode:
        raise HTTPException(status_code=401, detail="暗号不对，再试一次")
    response.set_cookie(
        COOKIE_NAME,
        create_session_token(),
        max_age=60 * 60 * 24 * 45,
        httponly=True,
        secure=False,
        samesite="lax",
    )
    return {"ok": True}


@app.get("/api/records")
def list_records(request: Request, q: str = "", tag: str = "", category: str = "") -> list[MomentRecord]:
    require_session(request)
    return store.list_records(q=q, tag=tag, category=category)


@app.post("/api/analyze")
async def analyze_only(request: Request, photo: UploadFile = File(...)):
    require_session(request)
    data = await photo.read()
    try:
        validate_image(photo.content_type or "", data, settings.max_upload_mb)
        record_id = uuid4().hex
        with TemporaryDirectory() as temp_dir:
            paths = make_images(data, Path(temp_dir), record_id)
            return analyze_image(paths["original"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/records")
async def create_record(
    request: Request,
    background_tasks: BackgroundTasks,
    photo: UploadFile = File(...),
) -> MomentRecord:
    require_session(request)
    data = await photo.read()
    try:
        validate_image(photo.content_type or "", data, settings.max_upload_mb)
        record_id = uuid4().hex
        paths = make_images(data, data_dir, record_id)
        urls = store.save_image_set(paths, record_id)
        analysis = fallback_analysis("analyzing")
        analysis.title = "识别中..."
        analysis.caption = "先收进相册了，AI 正在补上标题、标签和细节。"
        analysis.tags = ["识别中"]
        record = MomentRecord.from_analysis(record_id=record_id, analysis=analysis, **urls)
        saved = store.save_record(record)
        background_tasks.add_task(
            finish_record_analysis,
            record_id,
            str(paths["original"]),
            str(paths["cropped"]),
        )
        return saved
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def finish_record_analysis(record_id: str, original_path: str, cropped_path: str) -> None:
    try:
        analysis = analyze_image(Path(original_path))
    except Exception as exc:
        analysis = fallback_analysis(f"ai_error:{exc.__class__.__name__}")
    try:
        restyle_card_for_analysis(
            Path(original_path),
            Path(cropped_path),
            is_food=analysis.is_food,
            mood_color=analysis.mood_color,
        )
        store.replace_cropped_image(Path(cropped_path), record_id)
        store.update_analysis(record_id, analysis)
    except KeyError:
        pass


@app.patch("/api/records/{record_id}")
def update_record(record_id: str, patch: RecordPatch, request: Request) -> MomentRecord:
    require_session(request)
    try:
        return store.update_record(record_id, patch)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="找不到这条记录") from exc


@app.delete("/api/records/{record_id}")
def delete_record(record_id: str, request: Request) -> dict[str, bool]:
    require_session(request)
    try:
        store.delete_record(record_id)
        return {"ok": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="找不到这条记录") from exc


@app.get("/api/me/export")
def export_records(request: Request) -> JSONResponse:
    require_session(request)
    return JSONResponse(store.export_records(), headers={"Content-Disposition": "attachment; filename=shiguang-export.json"})
