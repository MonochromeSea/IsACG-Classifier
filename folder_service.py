import json
import os
import shutil
import string
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
MOVE_MODES = {"move", "copy", "hardlink", "symlink"}

DEFAULT_SETTINGS = {
    "source_dir": "",
    "output_dir_acg": "",
    "output_dir_non_acg": "",
    "path_layers": 0,
    "thread_count": 2,
    "auto_watch": False,
    "watch_interval": 3,
    "recursive": True,
    "auto_move": True,
    "auto_move_watch": True,
    "move_mode": "move",
    "model": "v1s",
}


def to_absolute(path_value: str) -> str:
    if not path_value:
        return ""
    return str(Path(path_value).expanduser().resolve())


class SettingsManager:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save(DEFAULT_SETTINGS.copy())

    def load(self) -> dict[str, Any]:
        with self.lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                data = {}
            merged = DEFAULT_SETTINGS.copy()
            merged.update({key: value for key, value in data.items() if key in DEFAULT_SETTINGS})
            merged["source_dir"] = to_absolute(str(merged.get("source_dir", "")))
            merged["output_dir_acg"] = to_absolute(str(merged.get("output_dir_acg", "")))
            merged["output_dir_non_acg"] = to_absolute(str(merged.get("output_dir_non_acg", "")))
            merged["thread_count"] = max(1, min(int(merged.get("thread_count", 2)), 32))
            merged["watch_interval"] = max(1, min(int(merged.get("watch_interval", 3)), 60))
            merged["move_mode"] = (
                merged.get("move_mode") if merged.get("move_mode") in MOVE_MODES else "move"
            )
            merged["auto_move_watch"] = bool(merged.get("auto_move_watch", True))
            return merged

    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            clean = DEFAULT_SETTINGS.copy()
            clean.update({key: value for key, value in data.items() if key in DEFAULT_SETTINGS})
            clean["source_dir"] = to_absolute(str(clean.get("source_dir", "")))
            clean["output_dir_acg"] = to_absolute(str(clean.get("output_dir_acg", "")))
            clean["output_dir_non_acg"] = to_absolute(str(clean.get("output_dir_non_acg", "")))
            clean["thread_count"] = max(1, min(int(clean.get("thread_count", 2)), 32))
            clean["watch_interval"] = max(1, min(int(clean.get("watch_interval", 3)), 60))
            clean["path_layers"] = max(0, int(clean.get("path_layers", 0)))
            clean["auto_watch"] = bool(clean.get("auto_watch", False))
            clean["recursive"] = bool(clean.get("recursive", True))
            clean["auto_move"] = bool(clean.get("auto_move", True))
            clean["auto_move_watch"] = bool(clean.get("auto_move_watch", True))
            clean["move_mode"] = (
                clean.get("move_mode") if clean.get("move_mode") in MOVE_MODES else "move"
            )
            self.path.write_text(
                json.dumps(clean, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return clean


class FileBrowser:
    @staticmethod
    def roots() -> list[dict[str, Any]]:
        if os.name == "nt":
            entries = []
            for letter in string.ascii_uppercase:
                root = f"{letter}:\\"
                if os.path.exists(root):
                    entries.append(
                        {
                            "name": f"{letter}:",
                            "path": root,
                            "type": "dir",
                            "size": None,
                            "mtime": None,
                        }
                    )
            return entries
        return [
            {
                "name": "/",
                "path": "/",
                "type": "dir",
                "size": None,
                "mtime": None,
            }
        ]

    @staticmethod
    def browse(path_value: str) -> dict[str, Any]:
        if not path_value:
            return {"current": "", "parent": None, "entries": FileBrowser.roots()}

        current = Path(path_value).expanduser().resolve()
        if not current.exists():
            raise FileNotFoundError("路径不存在")
        if not current.is_dir():
            raise NotADirectoryError("目标不是文件夹")

        entries = []
        try:
            children = list(current.iterdir())
        except PermissionError:
            children = []

        for child in children:
            try:
                is_dir = child.is_dir()
                is_image = child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS
            except OSError:
                continue
            if not is_dir and not is_image:
                continue
            stat = child.stat()
            entries.append(
                {
                    "name": child.name,
                    "path": str(child.resolve()),
                    "type": "dir" if is_dir else "file",
                    "size": stat.st_size if child.is_file() else None,
                    "mtime": stat.st_mtime,
                }
            )

        entries.sort(key=lambda item: (item["type"] != "dir", item["name"].lower()))
        return {
            "current": str(current),
            "parent": str(current.parent) if current.parent != current else None,
            "entries": entries,
        }


class FolderProcessor:
    def __init__(self, engine, settings_manager: SettingsManager):
        self.engine = engine
        self.settings_manager = settings_manager

    def scan_images(
        self,
        source_dir: str,
        recursive: bool = True,
        output_dirs: list[str] | None = None,
        progress_callback=None,
    ) -> list[Path]:
        source = Path(source_dir).expanduser().resolve()
        if not source.exists() or not source.is_dir():
            return []

        outputs = []
        for output_dir in output_dirs or []:
            if output_dir:
                outputs.append(Path(output_dir).expanduser().resolve())
        candidates = source.rglob("*") if recursive else source.glob("*")
        images = []
        source_resolved = source.resolve()
        for candidate in candidates:
            try:
                if not candidate.is_file() or candidate.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                resolved = candidate.resolve()
                should_skip = False
                for output in outputs:
                    output_resolved = output.resolve()
                    is_nested_output = (
                        output_resolved != source_resolved
                        and source_resolved in output_resolved.parents
                    )
                    if is_nested_output and (
                        output_resolved == resolved
                        or output_resolved in resolved.parents
                    ):
                        should_skip = True
                        break
                if should_skip:
                    continue
                images.append(resolved)
                if progress_callback:
                    progress_callback(len(images), None)
            except OSError:
                continue
        return sorted(images)

    def classify_paths(
        self,
        paths: list[Path],
        model_id: str,
        thread_count: int,
        progress_callback=None,
    ) -> list[dict[str, Any]]:
        thread_count = max(1, min(int(thread_count), 32))
        results: dict[Path, dict[str, Any]] = {}

        def classify_one(path: Path) -> tuple[Path, dict[str, Any]]:
            try:
                with Image.open(path) as image:
                    image = image.convert("RGB")
                result = self.engine.predict(image, model_id)
                result["path"] = str(path)
                result["filename"] = path.name
                return path, result
            except (UnidentifiedImageError, OSError, ValueError):
                return path, {"path": str(path), "filename": path.name, "error": "无法读取图片"}
            except Exception:
                return path, {"path": str(path), "filename": path.name, "error": "识别失败"}

        if len(paths) == 1:
            path, result = classify_one(paths[0])
            if progress_callback:
                progress_callback(1, 1)
            return [result]

        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = [executor.submit(classify_one, path) for path in paths]
            processed = 0
            for future in as_completed(futures):
                path, result = future.result()
                results[path] = result
                processed += 1
                if progress_callback:
                    progress_callback(processed, len(paths))
        return [results[path] for path in paths]

    def move_file(
        self,
        source_path: Path,
        target: str,
        source_dir: str,
        output_dir_acg: str,
        output_dir_non_acg: str,
        path_layers: int,
        move_mode: str = "move",
    ) -> dict[str, Any]:
        if target not in {"acg", "non_acg"}:
            raise ValueError("unsupported move target")
        if move_mode not in MOVE_MODES:
            move_mode = "move"

        source_path = source_path.resolve()
        source_dir_path = Path(source_dir).expanduser().resolve()
        output_dir_value = output_dir_acg if target == "acg" else output_dir_non_acg
        if not output_dir_value:
            return {"moved": False, "reason": "output_not_configured", "path": str(source_path)}
        output_dir_path = Path(output_dir_value).expanduser().resolve()
        if not source_path.exists():
            return {"moved": False, "reason": "not_found", "path": str(source_path)}

        try:
            relative_parts = source_path.relative_to(source_dir_path).parts
        except ValueError:
            relative_parts = (source_path.name,)

        if path_layers > 0:
            kept_parts = relative_parts[-(path_layers + 1) :]
        else:
            kept_parts = (relative_parts[-1],)

        destination = output_dir_path.joinpath(*kept_parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            return {
                "moved": False,
                "reason": "exists",
                "path": str(source_path),
                "destination": str(destination),
            }

        try:
            if move_mode == "move":
                shutil.move(str(source_path), str(destination))
            elif move_mode == "copy":
                shutil.copy2(str(source_path), str(destination))
            elif move_mode == "hardlink":
                os.link(str(source_path), str(destination))
            elif move_mode == "symlink":
                os.symlink(str(source_path), str(destination))
        except PermissionError as exc:
            return {
                "moved": False,
                "reason": "permission_denied",
                "error": "没有写入权限，请选择其他输出目录",
                "detail": str(exc),
                "path": str(source_path),
                "destination": str(destination),
            }
        except OSError as exc:
            return {
                "moved": False,
                "reason": f"{move_mode}_failed",
                "error": str(exc),
                "path": str(source_path),
                "destination": str(destination),
            }

        return {
            "moved": True,
            "reason": move_mode,
            "path": str(source_path),
            "destination": str(destination),
        }

    def classify_and_move(
        self,
        paths: list[Path],
        model_id: str,
        thread_count: int,
        source_dir: str,
        output_dir_acg: str,
        output_dir_non_acg: str,
        path_layers: int,
        auto_move: bool,
        move_mode: str = "move",
    ) -> list[dict[str, Any]]:
        results = self.classify_paths(paths, model_id, thread_count)
        if auto_move:
            for result in results:
                if result.get("error"):
                    result["move"] = {"moved": False, "reason": "recognition_error"}
                    continue
                target = "acg" if result.get("is_acg") else "non_acg"
                result["move"] = self.move_file(
                    Path(result["path"]),
                    target,
                    source_dir,
                    output_dir_acg,
                    output_dir_non_acg,
                    path_layers,
                    move_mode,
                )
        return results


class FolderWatcher:
    def __init__(self, settings_manager: SettingsManager, processor: FolderProcessor):
        self.settings_manager = settings_manager
        self.processor = processor
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.lock = threading.RLock()
        self.processed: set[str] = set()
        self.recent: list[dict[str, Any]] = []
        self.logs: list[dict[str, Any]] = []
        self.processed_count = 0
        self.last_scan = None
        self.last_error = ""

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run, name="folder-watcher", daemon=True)
            self.thread.start()
            self.log("自动监控已启动")

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        self.thread = None
        self.log("自动监控已停止")

    def log(self, message: str):
        with self.lock:
            self.logs.append({"time": time.time(), "message": message})
            self.logs = self.logs[-100:]

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {
                "running": bool(self.thread and self.thread.is_alive()),
                "processed_count": self.processed_count,
                "last_scan": self.last_scan,
                "last_error": self.last_error,
                "recent": self.recent[-20:],
                "logs": self.logs[-100:],
            }

    def _run(self):
        while not self.stop_event.is_set():
            settings = self.settings_manager.load()
            if not settings.get("auto_watch") or not settings.get("source_dir"):
                self.stop_event.wait(1)
                continue

            try:
                self._scan_once(settings)
            except Exception as exc:
                self.last_error = str(exc)
            self.last_scan = datetime.now().isoformat(timespec="seconds")
            self.stop_event.wait(max(1, int(settings.get("watch_interval", 3))))

    def _scan_once(self, settings: dict[str, Any]):
        source_dir = settings["source_dir"]
        output_dir_acg = settings.get("output_dir_acg", "")
        output_dir_non_acg = settings.get("output_dir_non_acg", "")
        paths = self.processor.scan_images(
            source_dir,
            recursive=settings.get("recursive", True),
            output_dirs=[output_dir_acg, output_dir_non_acg],
        )
        new_paths = [path for path in paths if str(path) not in self.processed]
        if not new_paths:
            return

        results = self.processor.classify_and_move(
            new_paths,
            model_id=settings.get("model", "v1s"),
            thread_count=settings.get("thread_count", 2),
            source_dir=source_dir,
            output_dir_acg=output_dir_acg,
            output_dir_non_acg=output_dir_non_acg,
            path_layers=int(settings.get("path_layers", 0)),
            auto_move=bool(settings.get("auto_move_watch", True)),
            move_mode=settings.get("move_mode", "move"),
        )
        with self.lock:
            self.processed_count += len(results)
            self.recent.extend(results)
            self.recent = self.recent[-100:]
            for result in results:
                if result.get("error"):
                    self.logs.append(
                        {
                            "time": time.time(),
                            "message": f"自动监控识别失败：{result.get('filename', '未知文件')}",
                        }
                    )
                else:
                    label = "ACG" if result.get("is_acg") else "非 ACG"
                    move = result.get("move") or {}
                    if move.get("moved"):
                        self.logs.append(
                            {
                                "time": time.time(),
                                "message": f"自动监控已处理：{result.get('filename', '未知文件')} -> {label}",
                            }
                        )
                    else:
                        self.logs.append(
                            {
                                "time": time.time(),
                                "message": f"自动监控已识别：{result.get('filename', '未知文件')} -> {label}（未移动）",
                            }
                        )
            self.logs = self.logs[-100:]
            for path in new_paths:
                self.processed.add(str(path))


settings_manager = SettingsManager(Path(__file__).resolve().parent / "config" / "settings.json")
