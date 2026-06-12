from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .config import settings
from .models import MomentAnalysis, MomentRecord, RecordPatch


class Store(Protocol):
    def save_record(self, record: MomentRecord) -> MomentRecord: ...
    def list_records(self, q: str = "", tag: str = "", category: str = "") -> list[MomentRecord]: ...
    def update_record(self, record_id: str, patch: RecordPatch) -> MomentRecord: ...
    def update_analysis(self, record_id: str, analysis: MomentAnalysis) -> MomentRecord: ...
    def delete_record(self, record_id: str) -> None: ...
    def export_records(self) -> list[dict[str, Any]]: ...
    def save_image_set(self, paths: dict[str, Path], record_id: str) -> dict[str, str]: ...
    def replace_cropped_image(self, cropped_path: Path, record_id: str) -> None: ...


class LocalStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.records_path = data_dir / "records.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.records_path.exists():
            self.records_path.write_text("[]", encoding="utf-8")

    def _read(self) -> list[dict[str, Any]]:
        return json.loads(self.records_path.read_text(encoding="utf-8"))

    def _write(self, rows: list[dict[str, Any]]) -> None:
        self.records_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_record(self, record: MomentRecord) -> MomentRecord:
        rows = self._read()
        rows.insert(0, record.model_dump(mode="json"))
        self._write(rows)
        return record

    def list_records(self, q: str = "", tag: str = "", category: str = "") -> list[MomentRecord]:
        rows = self._read()
        records = [MomentRecord(**row) for row in rows]
        q = q.strip().lower()
        tag = tag.strip()
        category = category.strip()
        if q:
            records = [
                item
                for item in records
                if q in " ".join([item.title, item.caption, item.notes, *item.tags, *item.objects]).lower()
            ]
        if tag:
            records = [item for item in records if tag in item.tags]
        if category:
            records = [item for item in records if item.category == category]
        return sorted(records, key=lambda item: item.created_at, reverse=True)

    def update_record(self, record_id: str, patch: RecordPatch) -> MomentRecord:
        rows = self._read()
        for index, row in enumerate(rows):
            if row["id"] == record_id:
                updates = patch.model_dump(exclude_unset=True)
                row.update(updates)
                row["updated_at"] = datetime.now(timezone.utc).isoformat()
                rows[index] = row
                self._write(rows)
                return MomentRecord(**row)
        raise KeyError(record_id)

    def update_analysis(self, record_id: str, analysis: MomentAnalysis) -> MomentRecord:
        rows = self._read()
        for index, row in enumerate(rows):
            if row["id"] == record_id:
                updates = analysis.model_dump()
                row.update(updates)
                row["raw_analysis"] = analysis.model_dump()
                row["updated_at"] = datetime.now(timezone.utc).isoformat()
                rows[index] = row
                self._write(rows)
                return MomentRecord(**row)
        raise KeyError(record_id)

    def delete_record(self, record_id: str) -> None:
        rows = self._read()
        removed = [row for row in rows if row["id"] == record_id]
        next_rows = [row for row in rows if row["id"] != record_id]
        if len(next_rows) == len(rows):
            raise KeyError(record_id)
        self._write(next_rows)
        for row in removed:
            self._delete_local_images(row)

    def export_records(self) -> list[dict[str, Any]]:
        return self._read()

    def save_image_set(self, paths: dict[str, Path], record_id: str) -> dict[str, str]:
        return {
            "original_url": f"/data/photos/original/{record_id}.jpg",
            "image_url": f"/data/photos/cropped/{record_id}.jpg",
            "thumbnail_url": f"/data/photos/thumbs/{record_id}.jpg",
        }

    def replace_cropped_image(self, cropped_path: Path, record_id: str) -> None:
        return None

    def _delete_local_images(self, row: dict[str, Any]) -> None:
        for field in ("original_url", "image_url", "thumbnail_url"):
            value = row.get(field, "")
            if not isinstance(value, str) or not value.startswith("/data/"):
                continue
            path = self.data_dir / value.removeprefix("/data/")
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


class SupabaseStore:
    def __init__(self):
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase storage requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        self.url = settings.supabase_url
        self.key = settings.supabase_service_role_key
        self.bucket = settings.supabase_storage_bucket

    def _request(self, method: str, path: str, body: Any | None = None, headers: dict[str, str] | None = None) -> Any:
        payload = None
        request_headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if headers:
            request_headers.update(headers)
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(f"{self.url}{path}", data=payload, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Supabase {method} {path} failed: {exc.code} {detail}") from exc

    def save_record(self, record: MomentRecord) -> MomentRecord:
        result = self._request(
            "POST",
            "/rest/v1/moment_records",
            record.model_dump(mode="json"),
            {"Prefer": "return=representation"},
        )
        return MomentRecord(**result[0])

    def list_records(self, q: str = "", tag: str = "", category: str = "") -> list[MomentRecord]:
        params = {"select": "*", "order": "created_at.desc"}
        if category:
            params["category"] = f"eq.{category}"
        path = "/rest/v1/moment_records?" + urllib.parse.urlencode(params)
        rows = self._request("GET", path) or []
        records = [MomentRecord(**row) for row in rows]
        q = q.strip().lower()
        tag = tag.strip()
        if q:
            records = [
                item
                for item in records
                if q in " ".join([item.title, item.caption, item.notes, *item.tags, *item.objects]).lower()
            ]
        if tag:
            records = [item for item in records if tag in item.tags]
        return records

    def update_record(self, record_id: str, patch: RecordPatch) -> MomentRecord:
        updates = patch.model_dump(exclude_unset=True)
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        encoded_id = urllib.parse.quote(record_id)
        result = self._request(
            "PATCH",
            f"/rest/v1/moment_records?id=eq.{encoded_id}",
            updates,
            {"Prefer": "return=representation"},
        )
        if not result:
            raise KeyError(record_id)
        return MomentRecord(**result[0])

    def update_analysis(self, record_id: str, analysis: MomentAnalysis) -> MomentRecord:
        updates = analysis.model_dump()
        updates["raw_analysis"] = analysis.model_dump()
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        encoded_id = urllib.parse.quote(record_id)
        result = self._request(
            "PATCH",
            f"/rest/v1/moment_records?id=eq.{encoded_id}",
            updates,
            {"Prefer": "return=representation"},
        )
        if not result:
            raise KeyError(record_id)
        return MomentRecord(**result[0])

    def delete_record(self, record_id: str) -> None:
        existing = self.list_records()
        target = next((record for record in existing if record.id == record_id), None)
        if target is None:
            raise KeyError(record_id)
        encoded_id = urllib.parse.quote(record_id)
        self._request("DELETE", f"/rest/v1/moment_records?id=eq.{encoded_id}")
        self._delete_remote_images(record_id)

    def export_records(self) -> list[dict[str, Any]]:
        return [record.model_dump(mode="json") for record in self.list_records()]

    def save_image_set(self, paths: dict[str, Path], record_id: str) -> dict[str, str]:
        urls: dict[str, str] = {}
        mapping = {
            "original": ("original_url", paths["original"]),
            "cropped": ("image_url", paths["cropped"]),
            "thumbs": ("thumbnail_url", paths["thumb"]),
        }
        for folder, (field, path) in mapping.items():
            object_path = f"{folder}/{record_id}.jpg"
            upload_url = f"{self.url}/storage/v1/object/{self.bucket}/{object_path}"
            request = urllib.request.Request(
                upload_url,
                data=path.read_bytes(),
                headers={
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "image/jpeg",
                    "x-upsert": "true",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=45):
                    pass
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                raise RuntimeError(f"Supabase storage upload failed: {exc.code} {detail}") from exc
            urls[field] = f"{self.url}/storage/v1/object/public/{self.bucket}/{object_path}"
        return urls

    def replace_cropped_image(self, cropped_path: Path, record_id: str) -> None:
        object_path = f"cropped/{record_id}.jpg"
        request = urllib.request.Request(
            f"{self.url}/storage/v1/object/{self.bucket}/{object_path}",
            data=cropped_path.read_bytes(),
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "image/jpeg",
                "x-upsert": "true",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45):
                pass
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Supabase cropped image replacement failed: {exc.code} {detail}") from exc

    def _delete_remote_images(self, record_id: str) -> None:
        paths = [f"original/{record_id}.jpg", f"cropped/{record_id}.jpg", f"thumbs/{record_id}.jpg"]
        try:
            self._request("DELETE", f"/storage/v1/object/{self.bucket}", paths)
        except RuntimeError:
            pass


def create_store() -> Store:
    if settings.storage_backend == "supabase":
        return SupabaseStore()
    return LocalStore(settings.data_dir)
