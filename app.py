import io
import os
import secrets
import time
from pathlib import Path

import folder_service
import job_service
import numpy as np
import onnxruntime as ort
from flask import Flask, abort, jsonify, render_template, request, send_file
from PIL import Image, UnidentifiedImageError


BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()

MODELS = {
    "v1s": {
        "file": "IsACG_v1s_98.94%.onnx",
        "name": "v1s",
        "title": "v1s 轻量",
        "description": "体积小、速度快，适合 NAS 与日常使用",
    },
    "v1": {
        "file": "IsACG_v1_99.06%.onnx",
        "name": "v1",
        "title": "v1 高精度",
        "description": "精度最高，推理速度稍慢",
    },
    "v2": {
        "file": "IsACG_v2_97.53%.onnx",
        "name": "v2",
        "title": "v2 泛化",
        "description": "更注重泛化能力，适合复杂来源图片",
    },
}

DEFAULT_MODEL = "v1s"
MAX_FILES = 40
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
MOVE_TARGETS = {"acg", "non_acg"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024


@app.after_request
def disable_static_cache(response):
    if request.path == "/" or request.path == "/settings" or request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


class IsACGEngine:
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.sessions: dict[str, ort.InferenceSession] = {}
        self.input_names: dict[str, str] = {}
        self.load_all()

    def load_all(self):
        for model_id, model_info in MODELS.items():
            model_path = self.model_dir / model_info["file"]
            if not model_path.exists():
                raise FileNotFoundError(f"模型文件不存在: {model_path}")
            session = ort.InferenceSession(
                str(model_path), providers=["CPUExecutionProvider"]
            )
            self.sessions[model_id] = session
            self.input_names[model_id] = session.get_inputs()[0].name

    def preprocess(self, image: Image.Image) -> np.ndarray:
        image = image.convert("RGB")
        image = image.resize((512, 512), Image.Resampling.BILINEAR)
        image_array = np.asarray(image, dtype=np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        image_array = (image_array - mean) / std
        image_array = np.transpose(image_array, (2, 0, 1))
        return np.expand_dims(image_array, axis=0)

    @staticmethod
    def softmax(values: np.ndarray) -> np.ndarray:
        shifted = values - np.max(values)
        exp_values = np.exp(shifted)
        return exp_values / np.sum(exp_values)

    def predict(self, image: Image.Image, model_id: str) -> dict:
        if model_id not in self.sessions:
            model_id = DEFAULT_MODEL

        started = time.perf_counter()
        session = self.sessions[model_id]
        input_name = self.input_names[model_id]
        model_input = self.preprocess(image)
        raw_output = session.run(None, {input_name: model_input})[0][0]
        probabilities = self.softmax(raw_output)
        predicted = int(np.argmax(probabilities))
        confidence = float(probabilities[predicted])
        elapsed_ms = (time.perf_counter() - started) * 1000

        return {
            "model": model_id,
            "is_acg": predicted == 1,
            "label": "ACG / 二次元风格" if predicted == 1 else "非 ACG 风格",
            "confidence": round(confidence, 6),
            "scores": {
                "non_acg": round(float(probabilities[0]), 6),
                "acg": round(float(probabilities[1]), 6),
            },
            "elapsed_ms": round(elapsed_ms, 1),
        }


engine = IsACGEngine(MODEL_DIR)


class StorageManager:
    def __init__(self, root: Path):
        self.root = root
        self.inbox = root / "inbox"
        self.acg = root / "acg"
        self.non_acg = root / "non_acg"
        for folder in (self.inbox, self.acg, self.non_acg):
            folder.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, filename: str, content: bytes) -> tuple[str, Path]:
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            suffix = ".jpg"
        file_id = f"{secrets.token_hex(16)}{suffix}"
        destination = self.inbox / file_id
        destination.write_bytes(content)
        return file_id, destination

    def move(self, file_id: str, target: str) -> str | None:
        if target not in MOVE_TARGETS:
            raise ValueError("unsupported move target")
        if Path(file_id).name != file_id or "/" in file_id or "\\" in file_id:
            raise ValueError("invalid file id")

        source = self.inbox / file_id
        if not source.exists():
            return None

        destination_root = self.acg if target == "acg" else self.non_acg
        destination = destination_root / file_id
        if destination.exists():
            destination = destination_root / f"{secrets.token_hex(4)}_{file_id}"
        source.replace(destination)
        return destination.relative_to(self.root).as_posix()


storage = StorageManager(STORAGE_DIR)
settings_manager = folder_service.settings_manager
folder_processor = folder_service.FolderProcessor(engine, settings_manager)
folder_watcher = folder_service.FolderWatcher(settings_manager, folder_processor)
job_manager = job_service.JobManager()


def image_from_bytes(content: bytes) -> Image.Image:
    return Image.open(io.BytesIO(content)).convert("RGB")


@app.get("/")
def index():
    return render_template("index.html", models=MODELS, default_model=DEFAULT_MODEL)


@app.get("/settings")
def settings_page():
    return render_template("settings.html", models=MODELS)


@app.get("/api/models")
def list_models():
    return jsonify(
        {
            "default": DEFAULT_MODEL,
            "models": [
                {
                    "id": model_id,
                    "name": model_info["name"],
                    "title": model_info["title"],
                    "description": model_info["description"],
                }
                for model_id, model_info in MODELS.items()
            ],
        }
    )


@app.get("/api/settings")
def get_settings():
    return jsonify(settings_manager.load())


@app.post("/api/settings")
def update_settings():
    payload = request.get_json(silent=True) or {}
    saved = settings_manager.save(payload)
    if saved.get("auto_watch"):
        folder_watcher.start()
    else:
        folder_watcher.stop()
    return jsonify({"success": True, "settings": saved})


@app.get("/api/fs/browse")
def browse_filesystem():
    path_value = request.args.get("path", "")
    try:
        return jsonify(folder_service.FileBrowser.browse(path_value))
    except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@app.get("/api/fs/preview")
def preview_file():
    path_value = request.args.get("path", "")
    if not path_value:
        abort(400)
    path = Path(path_value).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in folder_service.IMAGE_EXTENSIONS:
        abort(404)
    return send_file(path)


@app.get("/api/fs/thumbnail")
def thumbnail_file():
    path_value = request.args.get("path", "")
    size = int(request.args.get("size", 96))
    size = max(32, min(size, 512))
    if not path_value:
        abort(400)
    path = Path(path_value).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in folder_service.IMAGE_EXTENSIONS:
        abort(404)

    image = Image.open(path).convert("RGB")
    image.thumbnail((size, size), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=82)
    buffer.seek(0)
    return send_file(buffer, mimetype="image/jpeg")


def _run_scan_job(job_id, source_dir, recursive, output_dir_acg, output_dir_non_acg):
    def progress(found, _):
        job_manager.update(
            job_id,
            progress=found,
            message=f"已扫描 {found} 张",
        )

    job_manager.update(job_id, message="正在扫描图片...", log="开始扫描")
    paths = folder_processor.scan_images(
        source_dir,
        recursive=recursive,
        output_dirs=[output_dir_acg, output_dir_non_acg],
        progress_callback=progress,
    )
    job_manager.update(
        job_id,
        status="done",
        progress=len(paths),
        total=len(paths),
        result={"count": len(paths), "paths": [str(path) for path in paths]},
        message=f"扫描完成，共 {len(paths)} 张",
        log=f"扫描完成，共 {len(paths)} 张",
    )


def _run_classify_job(job_id, settings):
    source_dir = settings.get("source_dir", "")
    output_dir_acg = settings.get("output_dir_acg", "")
    output_dir_non_acg = settings.get("output_dir_non_acg", "")
    model_id = settings.get("model", DEFAULT_MODEL)
    thread_count = int(settings.get("thread_count", 2))
    path_layers = int(settings.get("path_layers", 0))
    recursive = bool(settings.get("recursive", True))
    auto_move = bool(settings.get("auto_move", True))
    move_mode = settings.get("move_mode", "move")
    paths = settings.get("paths") or []

    job_manager.update(job_id, message="准备识别图片...", log="开始批量识别")
    if not paths:
        paths = folder_processor.scan_images(
            source_dir,
            recursive=recursive,
            output_dirs=[output_dir_acg, output_dir_non_acg],
        )

    paths = [Path(path).expanduser().resolve() for path in paths]
    total = len(paths)

    def classify_progress(done, _):
        job_manager.update(job_id, progress=done, total=total, message=f"识别中 {done}/{total}")

    results = folder_processor.classify_paths(
        paths,
        model_id=model_id,
        thread_count=thread_count,
        progress_callback=classify_progress,
    )
    job_manager.update(job_id, progress=total, total=total, message="识别完成", log=f"识别完成，共 {total} 张")

    if auto_move:
        job_manager.update(job_id, message="开始移动图片...", log="开始移动")
        for index, result in enumerate(results, start=1):
            if result.get("error"):
                result["move"] = {"moved": False, "reason": "recognition_error"}
            else:
                target = "acg" if result.get("is_acg") else "non_acg"
                result["move"] = folder_processor.move_file(
                    Path(result["path"]),
                    target,
                    source_dir,
                    output_dir_acg,
                    output_dir_non_acg,
                    path_layers,
                    move_mode,
                )
            job_manager.update(job_id, progress=index, total=total, message=f"移动中 {index}/{total}")
        job_manager.update(job_id, message="移动完成", log="移动完成")

    job_manager.update(
        job_id,
        status="done",
        result={"count": len(results), "model": model_id, "results": results},
        message="任务完成",
    )


def _run_move_job(job_id, settings):
    source_dir = settings.get("source_dir", "")
    output_dir_acg = settings.get("output_dir_acg", "")
    output_dir_non_acg = settings.get("output_dir_non_acg", "")
    path_layers = int(settings.get("path_layers", 0))
    move_mode = settings.get("move_mode", "move")
    results = settings.get("results") or []
    total = len(results)

    job_manager.update(job_id, total=total, message="准备移动图片...", log="开始移动")
    moved = []
    for index, item in enumerate(results, start=1):
        source_path = Path(item.get("path", "")).expanduser().resolve()
        if not source_path.exists():
            result = {"path": str(source_path), "moved": False, "reason": "not_found"}
        else:
            target = "acg" if item.get("is_acg") else "non_acg"
            result = folder_processor.move_file(
                source_path,
                target,
                source_dir,
                output_dir_acg,
                output_dir_non_acg,
                path_layers,
                move_mode,
            )
        moved.append(result)
        job_manager.update(job_id, progress=index, total=total, message=f"移动中 {index}/{total}")

    job_manager.update(
        job_id,
        status="done",
        result={"moved": moved},
        message="移动完成",
        log="移动完成",
    )


@app.get("/api/folder/scan-job")
def start_scan_job():
    source_dir = request.args.get("path", "")
    recursive = request.args.get("recursive", "true").lower() == "true"
    output_dir_acg = request.args.get("output_dir_acg", "")
    output_dir_non_acg = request.args.get("output_dir_non_acg", "")
    if not source_dir:
        return jsonify({"success": False, "error": "请选择源文件夹"}), 400
    job_id = job_manager.run(
        "scan",
        _run_scan_job,
        source_dir,
        recursive,
        output_dir_acg,
        output_dir_non_acg,
    )
    return jsonify({"success": True, "job_id": job_id})


@app.post("/api/folder/classify-job")
def start_classify_job():
    payload = request.get_json(silent=True) or {}
    if not payload.get("source_dir") and not payload.get("paths"):
        return jsonify({"success": False, "error": "请选择源文件夹"}), 400
    job_id = job_manager.run("classify", _run_classify_job, payload)
    return jsonify({"success": True, "job_id": job_id})


@app.post("/api/folder/move-job")
def start_move_job():
    payload = request.get_json(silent=True) or {}
    if not payload.get("source_dir") or not isinstance(payload.get("results"), list):
        return jsonify({"success": False, "error": "移动参数不完整"}), 400
    job_id = job_manager.run("move", _run_move_job, payload)
    return jsonify({"success": True, "job_id": job_id})


@app.get("/api/jobs/<job_id>")
def get_job(job_id):
    job = job_manager.get(job_id)
    if not job:
        return jsonify({"success": False, "error": "任务不存在"}), 404
    return jsonify({"success": True, "job": job})


@app.get("/api/folder/scan")
def scan_folder():
    source_dir = request.args.get("path", "")
    recursive = request.args.get("recursive", "true").lower() == "true"
    output_dir_acg = request.args.get("output_dir_acg", "")
    output_dir_non_acg = request.args.get("output_dir_non_acg", "")
    if not source_dir:
        return jsonify({"success": False, "error": "请选择源文件夹"}), 400
    paths = folder_processor.scan_images(
        source_dir,
        recursive=recursive,
        output_dirs=[output_dir_acg, output_dir_non_acg],
    )
    return jsonify(
        {
            "success": True,
            "count": len(paths),
            "paths": [str(path) for path in paths],
        }
    )


@app.post("/api/folder/classify")
def classify_folder():
    payload = request.get_json(silent=True) or {}
    source_dir = payload.get("source_dir", "")
    output_dir_acg = payload.get("output_dir_acg", "")
    output_dir_non_acg = payload.get("output_dir_non_acg", "")
    model_id = payload.get("model", DEFAULT_MODEL)
    thread_count = int(payload.get("thread_count", 2))
    path_layers = int(payload.get("path_layers", 0))
    recursive = bool(payload.get("recursive", True))
    auto_move = bool(payload.get("auto_move", True))
    move_mode = payload.get("move_mode", "move")
    if move_mode not in folder_service.MOVE_MODES:
        move_mode = "move"

    if model_id not in MODELS:
        model_id = DEFAULT_MODEL
    if not source_dir:
        return jsonify({"success": False, "error": "请选择源文件夹"}), 400

    explicit_paths = payload.get("paths")
    if explicit_paths:
        paths = [Path(path).expanduser().resolve() for path in explicit_paths]
    else:
        paths = folder_processor.scan_images(
            source_dir,
            recursive=recursive,
            output_dirs=[output_dir_acg, output_dir_non_acg],
        )

    results = folder_processor.classify_and_move(
        paths,
        model_id=model_id,
        thread_count=thread_count,
        source_dir=source_dir,
        output_dir_acg=output_dir_acg,
        output_dir_non_acg=output_dir_non_acg,
        path_layers=path_layers,
        auto_move=auto_move,
        move_mode=move_mode,
    )
    return jsonify(
        {
            "success": True,
            "count": len(results),
            "model": model_id,
            "results": results,
        }
    )


@app.post("/api/folder/move")
def move_folder_results():
    payload = request.get_json(silent=True) or {}
    source_dir = payload.get("source_dir", "")
    output_dir_acg = payload.get("output_dir_acg", "")
    output_dir_non_acg = payload.get("output_dir_non_acg", "")
    path_layers = int(payload.get("path_layers", 0))
    move_mode = payload.get("move_mode", "move")
    if move_mode not in folder_service.MOVE_MODES:
        move_mode = "move"
    results = payload.get("results")

    if not source_dir or not isinstance(results, list):
        return jsonify({"success": False, "error": "移动参数不完整"}), 400

    moved = []
    for item in results:
        source_path = Path(item.get("path", "")).expanduser().resolve()
        is_acg = bool(item.get("is_acg", False))
        if not source_path.exists():
            moved.append(
                {
                    "path": str(source_path),
                    "moved": False,
                    "reason": "not_found",
                }
            )
            continue
        target = "acg" if is_acg else "non_acg"
        move_result = folder_processor.move_file(
            source_path,
            target,
            source_dir,
            output_dir_acg,
            output_dir_non_acg,
            path_layers,
            move_mode,
        )
        moved.append(move_result)

    return jsonify({"success": True, "moved": moved})


@app.post("/api/watcher/start")
def start_watcher():
    settings = settings_manager.load()
    settings["auto_watch"] = True
    settings_manager.save(settings)
    folder_watcher.start()
    return jsonify({"success": True, "status": folder_watcher.status()})


@app.post("/api/watcher/stop")
def stop_watcher():
    settings = settings_manager.load()
    settings["auto_watch"] = False
    settings_manager.save(settings)
    folder_watcher.stop()
    return jsonify({"success": True, "status": folder_watcher.status()})


@app.get("/api/watcher/status")
def watcher_status():
    return jsonify(folder_watcher.status())


@app.post("/api/predict")
def predict():
    uploaded_files = request.files.getlist("files")
    if not uploaded_files:
        return jsonify({"success": False, "error": "请选择至少一张图片"}), 400
    if len(uploaded_files) > MAX_FILES:
        return jsonify({"success": False, "error": f"一次最多上传 {MAX_FILES} 张图片"}), 400

    model_id = request.form.get("model", DEFAULT_MODEL)
    if model_id not in MODELS:
        model_id = DEFAULT_MODEL

    results = []
    for file_storage in uploaded_files:
        filename = file_storage.filename or "未命名图片"
        content = file_storage.read()
        try:
            image = image_from_bytes(content)
            result = engine.predict(image, model_id)
            result["filename"] = filename
            file_id, _ = storage.save_bytes(filename, content)
            result["file_id"] = file_id
            result["stored_name"] = file_id
            results.append(result)
        except (UnidentifiedImageError, OSError, ValueError):
            results.append(
                {
                    "filename": filename,
                    "error": "文件不是可识别的图片",
                }
            )
        except Exception:
            results.append(
                {
                    "filename": filename,
                    "error": "这张图片处理失败",
                }
            )

    return jsonify({"success": True, "model": model_id, "results": results})


@app.post("/api/move")
def move_file():
    payload = request.get_json(silent=True) or {}
    file_id = payload.get("file_id")
    target = payload.get("target")

    if not file_id or target not in MOVE_TARGETS:
        return jsonify({"success": False, "error": "移动参数无效"}), 400

    try:
        relative_path = storage.move(file_id, target)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    if relative_path is None:
        return jsonify({"success": False, "error": "文件已移动或不存在"}), 404

    return jsonify(
        {
            "success": True,
            "file_id": file_id,
            "target": target,
            "path": relative_path,
        }
    )


@app.post("/api/move-batch")
def move_batch():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return jsonify({"success": False, "error": "没有可移动的文件"}), 400

    moved = []
    failed = []
    for item in items:
        file_id = item.get("file_id")
        target = item.get("target")
        if not file_id or target not in MOVE_TARGETS:
            failed.append({"file_id": file_id, "reason": "invalid target"})
            continue
        try:
            relative_path = storage.move(file_id, target)
        except ValueError:
            failed.append({"file_id": file_id, "reason": "invalid target"})
            continue

        if relative_path is None:
            failed.append({"file_id": file_id, "reason": "not found"})
            continue
        moved.append(
            {
                "file_id": file_id,
                "target": target,
                "path": relative_path,
            }
        )

    return jsonify({"success": True, "moved": moved, "failed": failed})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
