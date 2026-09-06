import json
import logging
import os
import shutil
import string
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from PIL import Image, UnidentifiedImageError

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    FileSystemEventHandler = None
    Observer = None


logger = logging.getLogger("isacg")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
MOVE_MODES = {"move", "copy", "hardlink", "symlink"}
WATCHDOG_AVAILABLE = FileSystemEventHandler is not None and Observer is not None


class ProcessingCancelled(Exception):
    pass


if FileSystemEventHandler is not None:
    class ImageEventHandler(FileSystemEventHandler):
        def __init__(self, event_queue: Queue):
            self.event_queue = event_queue

        def on_created(self, event):
            self._enqueue(event)

        def on_modified(self, event):
            self._enqueue(event)

        def on_moved(self, event):
            self._enqueue(event, moved=True)

        def _enqueue(self, event, moved: bool = False):
            if event.is_directory:
                return
            path_value = event.dest_path if moved and getattr(event, "dest_path", "") else event.src_path
            if Path(path_value).suffix.lower() in IMAGE_EXTENSIONS:
                self.event_queue.put(Path(path_value))
else:
    ImageEventHandler = None


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
    "watch_existing_files": True,
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
            merged["watch_existing_files"] = bool(merged.get("watch_existing_files", True))
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
            clean["watch_existing_files"] = bool(clean.get("watch_existing_files", True))
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
        should_stop=None,
    ) -> list[Path]:
        source = Path(source_dir).expanduser().resolve()
        if not source.exists() or not source.is_dir():
            return []

        outputs = []
        for output_dir in output_dirs or []:
            if output_dir:
                outputs.append(Path(output_dir).expanduser().resolve())
        source_resolved = source.resolve()
        nested_outputs = [
            output
            for output in outputs
            if output != source_resolved and source_resolved in output.parents
        ]
        images = []
        def is_output_or_inside(path: Path) -> bool:
            return any(output == path or output in path.parents for output in nested_outputs)

        def should_prune_directory(path: Path) -> bool:
            return any(output == path or path in output.parents for output in nested_outputs)

        def add_candidate(candidate: Path):
            try:
                if should_stop and should_stop():
                    return False
                if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
                    return True
                resolved = candidate.resolve()
                if is_output_or_inside(resolved):
                    return True
                if not resolved.is_file():
                    return True
                images.append(resolved)
                if progress_callback:
                    progress_callback(len(images), None)
            except OSError:
                pass
            return True

        if recursive:
            for root, directories, filenames in os.walk(source, topdown=True, followlinks=False):
                root_path = Path(root)
                directories[:] = [
                    name
                    for name in directories
                    if not should_prune_directory(root_path / name)
                ]
                for filename in filenames:
                    if not add_candidate(root_path / filename):
                        break
                if should_stop and should_stop():
                    break
        else:
            try:
                with os.scandir(source) as entries:
                    for entry in entries:
                        if entry.is_file():
                            if not add_candidate(Path(entry.path)):
                                break
            except OSError:
                pass
        return sorted(images)

    def classify_paths(
        self,
        paths: list[Path],
        model_id: str,
        thread_count: int,
        progress_callback=None,
        pause_callback=None,
        should_stop=None,
        status_callback=None,
        result_callback=None,
    ) -> list[dict[str, Any]]:
        thread_count = max(1, min(int(thread_count), 32))
        results: dict[Path, dict[str, Any]] = {}

        def classify_one(path: Path) -> tuple[Path, dict[str, Any]]:
            if should_stop and should_stop():
                raise ProcessingCancelled()
            if pause_callback:
                pause_callback()
            if should_stop and should_stop():
                raise ProcessingCancelled()
            if status_callback:
                status_callback("start", path, None)
            try:
                with Image.open(path) as image:
                    image = image.convert("RGB")
                result = self.engine.predict(image, model_id)
                result["path"] = str(path)
                result["filename"] = path.name
                if status_callback:
                    status_callback("done", path, result)
                return path, result
            except (UnidentifiedImageError, OSError, ValueError):
                result = {"path": str(path), "filename": path.name, "error": "无法读取图片"}
                if status_callback:
                    status_callback("error", path, result)
                return path, result
            except Exception:
                result = {"path": str(path), "filename": path.name, "error": "识别失败"}
                if status_callback:
                    status_callback("error", path, result)
                return path, result

        if len(paths) == 1:
            if should_stop and should_stop():
                return []
            try:
                path, result = classify_one(paths[0])
            except ProcessingCancelled:
                return []
            if result_callback:
                result_callback(path, result)
            if progress_callback:
                progress_callback(1, 1)
            return [result]

        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            pending = {}
            path_iterator = iter(paths)

            def submit_next() -> bool:
                try:
                    path = next(path_iterator)
                except StopIteration:
                    return False
                pending[executor.submit(classify_one, path)] = path
                return True

            for _ in range(min(len(paths), max(1, thread_count * 2))):
                submit_next()

            processed = 0
            while pending:
                if should_stop and should_stop():
                    for future in pending:
                        future.cancel()
                    break
                completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in completed:
                    pending.pop(future, None)
                    try:
                        path, result = future.result()
                    except ProcessingCancelled:
                        continue
                    if result_callback:
                        result_callback(path, result)
                    results[path] = result
                    processed += 1
                    if progress_callback:
                        progress_callback(processed, len(paths))
                    if not (should_stop and should_stop()):
                        submit_next()
        return [results[path] for path in paths if path in results]

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

    def undo_move(
        self,
        move_result: dict[str, Any],
        source_dir: str,
        output_dirs: list[str] | None = None,
    ) -> dict[str, Any]:
        if not move_result or not move_result.get("moved"):
            return {
                "undone": False,
                "reason": "not_moved",
                "path": move_result.get("path", "") if move_result else "",
            }

        source_path = Path(move_result.get("path", "")).expanduser().resolve()
        destination_value = move_result.get("destination", "")
        if not destination_value:
            return {
                "undone": False,
                "reason": "destination_missing",
                "path": str(source_path),
            }
        # Keep symlink paths lexical; resolve() would turn the destination into its source.
        destination = Path(destination_value).expanduser().absolute()

        source_root = Path(source_dir).expanduser().resolve()
        try:
            source_path.relative_to(source_root)
        except ValueError:
            return {
                "undone": False,
                "reason": "source_outside_configured_folder",
                "path": str(source_path),
                "destination": str(destination),
            }

        allowed_outputs = [
            Path(path).expanduser().resolve()
            for path in (output_dirs or [])
            if path
        ]
        if not any(
            destination == output or output in destination.parents
            for output in allowed_outputs
        ):
            return {
                "undone": False,
                "reason": "destination_outside_configured_folder",
                "path": str(source_path),
                "destination": str(destination),
            }

        mode = move_result.get("reason", "move")
        destination_exists = destination.exists() or destination.is_symlink()
        if not destination_exists:
            return {
                "undone": False,
                "reason": "destination_not_found",
                "path": str(source_path),
                "destination": str(destination),
            }
        if destination.is_dir():
            return {
                "undone": False,
                "reason": "destination_is_directory",
                "path": str(source_path),
                "destination": str(destination),
            }

        try:
            if mode == "move":
                if source_path.exists():
                    return {
                        "undone": False,
                        "reason": "source_exists",
                        "path": str(source_path),
                        "destination": str(destination),
                    }
                source_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source_path))
            elif mode in {"copy", "hardlink", "symlink"}:
                destination.unlink()
            else:
                return {
                    "undone": False,
                    "reason": "unsupported_move_mode",
                    "path": str(source_path),
                    "destination": str(destination),
                }
        except PermissionError as exc:
            return {
                "undone": False,
                "reason": "permission_denied",
                "error": "没有权限撤销这次文件处理",
                "detail": str(exc),
                "path": str(source_path),
                "destination": str(destination),
            }
        except OSError as exc:
            return {
                "undone": False,
                "reason": "undo_failed",
                "error": str(exc),
                "path": str(source_path),
                "destination": str(destination),
            }

        return {
            "undone": True,
            "reason": f"undo_{mode}",
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
        status_callback=None,
        progress_callback=None,
        pause_callback=None,
        should_stop=None,
        result_callback=None,
    ) -> list[dict[str, Any]]:
        def handle_result(path: Path, result: dict[str, Any]):
            if pause_callback:
                pause_callback()
            if should_stop and should_stop():
                return
            if auto_move:
                if result.get("error"):
                    result["move"] = {"moved": False, "reason": "recognition_error"}
                else:
                    target = "acg" if result.get("is_acg") else "non_acg"
                    result["move"] = self.move_file(
                        path,
                        target,
                        source_dir,
                        output_dir_acg,
                        output_dir_non_acg,
                        path_layers,
                        move_mode,
                    )
            if result_callback:
                result_callback(path, result)

        return self.classify_paths(
            paths,
            model_id,
            thread_count,
            progress_callback=progress_callback,
            pause_callback=pause_callback,
            should_stop=should_stop,
            status_callback=status_callback,
            result_callback=handle_result,
        )


class FolderWatcher:
    def __init__(self, settings_manager: SettingsManager, processor: FolderProcessor):
        self.settings_manager = settings_manager
        self.processor = processor
        self.state_path = settings_manager.path.parent / "watcher_state.json"
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.lock = threading.RLock()
        self.processed: dict[str, str] = {}
        self.recent: list[dict[str, Any]] = []
        self.logs: list[dict[str, Any]] = []
        self.event_queue: Queue[Path] = Queue()
        self.observer = None
        self.processed_count = 0
        self.last_scan = None
        self.last_error = ""
        self.phase = "idle"
        self.message = "监控未运行"
        self.monitor_mode = "idle"
        self.watchdog_available = WATCHDOG_AVAILABLE
        self.scan_count = 0
        self.pending_count = 0
        self.batch_total = 0
        self.batch_progress = 0
        self.current_file = ""
        self.event_debounce_seconds = 2.0
        self._load_state()

    def _load_state(self):
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            data = {}
        processed = data.get("processed", {})
        if isinstance(processed, dict):
            self.processed = {
                str(path): str(signature)
                for path, signature in processed.items()
                if path and signature
            }
        try:
            self.processed_count = max(0, int(data.get("processed_count", 0) or 0))
        except (TypeError, ValueError):
            self.processed_count = 0

    def _save_state(self):
        try:
            self.state_path.write_text(
                json.dumps(
                    {
                        "processed": self.processed,
                        "processed_count": self.processed_count,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    @staticmethod
    def _fingerprint(path: Path) -> str:
        stat = path.stat()
        return f"{stat.st_size}:{stat.st_mtime_ns}"

    def start(self, process_existing: bool = True):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.stop_event.clear()
            self.event_queue = Queue()
        with self.lock:
            self.thread = threading.Thread(
                target=self._run,
                args=(process_existing,),
                name="folder-watcher",
                daemon=True,
            )
            self.thread.start()
            self.phase = "idle"
            self.message = "自动监控已启动，等待新增图片"
            mode = "处理已有文件" if process_existing else "忽略已有文件，仅处理新增/修改"
            self.log(f"自动监控已启动（{mode}）")

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        self.thread = None
        with self.lock:
            self.phase = "stopped"
            self.message = "自动监控已停止"
            self.monitor_mode = "idle"
            self.pending_count = 0
            self.batch_total = 0
            self.batch_progress = 0
            self.current_file = ""
        self.log("自动监控已停止")

    def log(self, message: str):
        with self.lock:
            self.logs.append({"time": time.time(), "message": message})
            self.logs = self.logs[-100:]
        logger.info("[watcher] %s", message)

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {
                "running": bool(self.thread and self.thread.is_alive()),
                "processed_count": self.processed_count,
                "last_scan": self.last_scan,
                "last_error": self.last_error,
                "phase": self.phase,
                "message": self.message,
                "monitor_mode": self.monitor_mode,
                "watchdog_available": self.watchdog_available,
                "scan_count": self.scan_count,
                "pending_count": self.pending_count,
                "batch_total": self.batch_total,
                "batch_progress": self.batch_progress,
                "current_file": self.current_file,
                "has_pending_task": self.pending_count > 0
                or self.phase in {"baselining", "scanning", "processing", "starting"},
                "recent": self.recent[-20:],
                "logs": self.logs[-100:],
            }

    def _set_runtime_state(self, **values):
        with self.lock:
            for key, value in values.items():
                setattr(self, key, value)

    def _baseline_current_files(self, settings: dict[str, Any]):
        source_dir = settings.get("source_dir", "")
        if not source_dir:
            return
        output_dir_acg = settings.get("output_dir_acg", "")
        output_dir_non_acg = settings.get("output_dir_non_acg", "")
        self._set_runtime_state(
            phase="baselining",
            message="正在登记已有图片，之后只处理新增/修改",
            scan_count=0,
            pending_count=0,
            batch_total=0,
            batch_progress=0,
            current_file="",
        )

        def progress(found, _):
            self._set_runtime_state(scan_count=found, message=f"正在登记已有图片：{found} 张")

        paths = self.processor.scan_images(
            source_dir,
            recursive=settings.get("recursive", True),
            output_dirs=[output_dir_acg, output_dir_non_acg],
            progress_callback=progress,
        )
        fingerprints = {}
        for path in paths:
            try:
                fingerprints[str(path)] = self._fingerprint(path)
            except OSError:
                continue
        with self.lock:
            self.processed.update(fingerprints)
            self.scan_count = len(paths)
            self.phase = "idle"
            self.message = f"已忽略当前已有 {len(paths)} 张图片，等待新增/修改"
            self._save_state()
        self.log(f"已登记当前已有 {len(paths)} 张图片，后续仅监控新增或修改")

    def _run(self, process_existing: bool = True):
        if WATCHDOG_AVAILABLE:
            self._run_event_watch(process_existing)
            return

        self.log("未安装 watchdog，自动监控回退为定时扫描模式")
        if not process_existing:
            settings = self.settings_manager.load()
            self._baseline_current_files(settings)
        self._run_polling_watch()

    def _run_polling_watch(self):
        self._set_runtime_state(monitor_mode="polling")
        while not self.stop_event.is_set():
            settings = self.settings_manager.load()
            if not settings.get("auto_watch") or not settings.get("source_dir"):
                self.stop_event.wait(1)
                continue

            try:
                self._scan_once(settings)
            except Exception as exc:
                self.last_error = str(exc)
                self._set_runtime_state(phase="error", message=f"自动监控异常：{exc}")
            self.last_scan = datetime.now().isoformat(timespec="seconds")
            self.stop_event.wait(max(1, int(settings.get("watch_interval", 3))))

    def _run_event_watch(self, process_existing: bool):
        settings = self.settings_manager.load()
        if not settings.get("source_dir"):
            self._set_runtime_state(phase="error", message="未设置源文件夹")
            return
        source = Path(settings["source_dir"]).expanduser().resolve()
        if not source.exists() or not source.is_dir():
            self._set_runtime_state(phase="error", message="源文件夹不存在")
            return

        self._set_runtime_state(
            monitor_mode="event",
            phase="starting",
            message="正在启动事件监控",
            pending_count=0,
            batch_total=0,
            batch_progress=0,
            current_file="",
        )

        if process_existing:
            try:
                self._scan_once(settings)
            except Exception as exc:
                self.last_error = str(exc)
                self._set_runtime_state(phase="error", message=f"启动扫描异常：{exc}")

        pending: dict[Path, float] = {}
        observer = Observer()
        handler = ImageEventHandler(self.event_queue)
        observer.schedule(handler, str(source), recursive=bool(settings.get("recursive", True)))
        self.observer = observer
        observer.start()
        self.log(f"自动监控使用事件模式（watchdog/inotify）：{source}")
        if not process_existing:
            self._set_runtime_state(
                phase="idle",
                message="已忽略启动前已有文件，等待新增/修改",
                scan_count=0,
            )

        try:
            while not self.stop_event.is_set():
                settings = self.settings_manager.load()
                if not settings.get("auto_watch"):
                    self.stop_event.wait(1)
                    continue

                now = time.monotonic()
                try:
                    while True:
                        path = self.event_queue.get_nowait()
                        pending[path.expanduser().resolve()] = now
                except Empty:
                    pass

                ready = [
                    path
                    for path, first_seen in pending.items()
                    if now - first_seen >= self.event_debounce_seconds
                ]
                if ready:
                    for path in ready:
                        pending.pop(path, None)
                    try:
                        self._process_paths(settings, ready, source_total=None)
                    except Exception as exc:
                        self.last_error = str(exc)
                        self._set_runtime_state(phase="error", message=f"自动监控异常：{exc}")
                    self.last_scan = datetime.now().isoformat(timespec="seconds")
                    continue

                self._set_runtime_state(
                    phase="idle",
                    message="自动监控运行中，等待新增/修改图片",
                    pending_count=len(pending),
                    batch_total=0,
                    batch_progress=0,
                    current_file="",
                )
                self.stop_event.wait(0.5)
        finally:
            observer.stop()
            observer.join(timeout=2)
            self.observer = None

    def _scan_once(self, settings: dict[str, Any]):
        source_dir = settings["source_dir"]
        output_dir_acg = settings.get("output_dir_acg", "")
        output_dir_non_acg = settings.get("output_dir_non_acg", "")
        self._set_runtime_state(
            phase="scanning",
            message="正在扫描源文件夹",
            scan_count=0,
            pending_count=0,
            batch_total=0,
            batch_progress=0,
            current_file="",
        )

        def scan_progress(found, _):
            self._set_runtime_state(scan_count=found, message=f"正在扫描源文件夹：{found} 张")

        paths = self.processor.scan_images(
            source_dir,
            recursive=settings.get("recursive", True),
            output_dirs=[output_dir_acg, output_dir_non_acg],
            progress_callback=scan_progress,
        )
        self._process_paths(settings, paths, source_total=len(paths))

    def _is_output_path(self, path: Path, settings: dict[str, Any]) -> bool:
        source_dir = settings.get("source_dir", "")
        if not source_dir:
            return False
        source_root = Path(source_dir).expanduser().resolve()
        outputs = [
            Path(output_dir).expanduser().resolve()
            for output_dir in (
                settings.get("output_dir_acg", ""),
                settings.get("output_dir_non_acg", ""),
            )
            if output_dir
        ]
        nested_outputs = [
            output
            for output in outputs
            if output != source_root and source_root in output.parents
        ]
        return any(output == path or output in path.parents for output in nested_outputs)

    def _wait_for_stable_fingerprint(self, path: Path) -> str | None:
        last_signature = None
        stable_count = 0
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not self.stop_event.is_set():
            try:
                if path.suffix.lower() not in IMAGE_EXTENSIONS or not path.is_file():
                    return None
                signature = self._fingerprint(path)
            except OSError:
                time.sleep(0.5)
                continue
            if signature == last_signature:
                stable_count += 1
                if stable_count >= 2:
                    return signature
            else:
                last_signature = signature
                stable_count = 0
            time.sleep(0.5)
        return last_signature

    def _process_paths(
        self,
        settings: dict[str, Any],
        paths: list[Path],
        source_total: int | None = None,
    ):
        source_dir = settings["source_dir"]
        output_dir_acg = settings.get("output_dir_acg", "")
        output_dir_non_acg = settings.get("output_dir_non_acg", "")
        fingerprints = {}
        candidates: list[Path] = []
        seen: set[str] = set()
        for path in paths:
            try:
                resolved = path.expanduser().resolve()
            except OSError:
                continue
            path_key = str(resolved)
            if path_key in seen:
                continue
            seen.add(path_key)
            if self._is_output_path(resolved, settings):
                continue
            signature = self._wait_for_stable_fingerprint(resolved)
            if not signature:
                continue
            candidates.append(resolved)
            fingerprints[path_key] = signature
        current_paths = set(fingerprints)
        source_root = Path(source_dir).expanduser().resolve()
        if source_total is not None:
            with self.lock:
                self.processed = {
                    path: signature
                    for path, signature in self.processed.items()
                    if not Path(path).is_relative_to(source_root) or path in current_paths
                }
        new_paths = [
            path
            for path in candidates
            if self.processed.get(str(path)) != fingerprints.get(str(path))
        ]
        if not new_paths:
            message = (
                f"未发现新增图片，已扫描 {source_total} 张"
                if source_total is not None
                else "收到文件变化，但没有可处理的新图片"
            )
            self._set_runtime_state(
                phase="idle",
                message=message,
                scan_count=source_total if source_total is not None else self.scan_count,
                pending_count=0,
                batch_total=0,
                batch_progress=0,
                current_file="",
            )
            return
        self._set_runtime_state(
            phase="processing",
            message=f"发现 {len(new_paths)} 张新增/修改图片，准备识别",
            pending_count=len(new_paths),
            batch_total=len(new_paths),
            batch_progress=0,
        )
        self.log(f"自动监控发现 {len(new_paths)} 张新图片或已修改图片")

        def watch_status(event, path, result):
            if event == "start":
                self._set_runtime_state(phase="processing", current_file=path.name)
                self.log(f"自动监控识别中：{path}")
                return
            if event == "error":
                self.log(f"自动监控识别失败：{path.name} · {result.get('error', '未知错误')}")
                return
            label = "ACG" if result.get("is_acg") else "非 ACG"
            confidence = float(result.get("confidence", 0)) * 100
            self.log(f"自动监控识别完成：{path.name} -> {label} · {confidence:.2f}%")

        def watch_result(path, result):
            with self.lock:
                self.batch_progress += 1
                self.pending_count = max(0, self.batch_total - self.batch_progress)
                self.current_file = path.name
                self.message = f"自动监控处理中 {self.batch_progress}/{self.batch_total}"

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
            status_callback=watch_status,
            result_callback=watch_result,
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
                signature = fingerprints.get(str(path))
                if signature:
                    self.processed[str(path)] = signature
            self.phase = "idle"
            self.message = f"自动监控本轮完成，共处理 {len(results)} 张"
            self.pending_count = 0
            self.batch_total = 0
            self.batch_progress = 0
            self.current_file = ""
            self._save_state()


settings_manager = SettingsManager(Path(__file__).resolve().parent / "config" / "settings.json")
