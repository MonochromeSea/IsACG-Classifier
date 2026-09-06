# 配置说明

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Web 服务监听地址 |
| `PORT` | `8080` | Web 服务端口 |
| `STORAGE_DIR` | `/app/storage` | 上传图片和默认结果目录 |
| `ISACG_DEVICE` | `CPU` | 推理设备，支持 `CPU`、`VULKAN`，Windows 本地可用 `DML` |
| `ISACG_PRELOAD_MODELS` | `v1s` | 启动时预加载的模型列表 |
| `ORT_INTRA_OP_THREADS` | `1` | ONNX Runtime 单次推理内部线程数 |
| `ORT_INTER_OP_THREADS` | `1` | ONNX Runtime 跨算子线程数 |
| `WAITRESS_THREADS` | `4` | Waitress Web 服务线程数 |
| `JOB_SAVE_INTERVAL` | `0.75` | 任务状态写盘最小间隔，单位秒 |
| `JOB_HISTORY_LIMIT` | `30` | 保留的历史任务数量 |
| `PYTHON_SLIM_IMAGE` | `docker.m.daocloud.io/library/python:3.12-slim-bookworm` | Vulkan 镜像的 Python 基础镜像 |
| `ISACG_RENDER_GID` | `0` | 容器访问 `/dev/dri/renderD*` 时使用的宿主机 render 组 GID |

更多自动监控选项保存在 `config/settings.json` 中，可在网页设置页调整：

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `watch_existing_files` | `true` | 启动监控时是否处理源目录已有未处理图片 |
| `auto_move_watch` | `true` | 监控识别后是否自动处理文件 |
| `watch_interval` | `3` | 自动监控轮询 fallback 的扫描间隔，单位秒；默认事件模式不按间隔扫盘 |

## 自动监控

自动监控默认使用 watchdog/inotify 事件模式，适合 NAS 长期运行。开启“忽略已有文件，仅处理新增/修改”时，服务不会先遍历源目录，而是等待新增、移动进入或修改图片事件；开启“处理所有未处理文件”时，会在启动监控时扫描一次已有文件，随后进入事件模式。

如果镜像或运行环境缺少 watchdog，程序会自动回退到轮询扫描模式，此时 `watch_interval` 才会生效。轮询模式会定期遍历源目录，但仍然只识别新增或文件指纹变化的图片，不会每次把全量图片重新识别一遍。

## 模型预加载

默认只预加载轻量模型：

```dotenv
ISACG_PRELOAD_MODELS=v1s
```

这样启动更快、内存占用更低。若希望切换模型时无需等待首次加载，可以改为：

```dotenv
ISACG_PRELOAD_MODELS=v1s,v1,v2
```

## 并发建议

NAS 或低功耗主机建议保持：

```dotenv
ORT_INTRA_OP_THREADS=1
ORT_INTER_OP_THREADS=1
```

然后在网页设置页里调节识别线程数。CPU 较强时，可以逐步提高识别线程数并观察单张耗时、CPU 占用和系统响应。

## 文件处理方式

| 方式 | 行为 | 适用场景 |
| --- | --- | --- |
| 移动 | 把源文件移动到分类结果目录 | 正式整理图库 |
| 复制 | 保留源文件并复制到结果目录 | 先验证分类效果 |
| 硬链接 | 创建同盘文件链接 | 同一文件系统内节省空间 |
| 软链接 | 创建符号链接 | 保留原文件位置并建立引用 |

撤销功能会尽量恢复本次任务产生的处理结果。移动模式会把文件移回原路径；复制、硬链接和软链接模式会删除创建出的目标文件。

## 保留路径层数

保留路径层数用于避免不同目录下的同名文件互相覆盖。

```text
原路径：/data/source/path3/path2/path1/file.jpg
保留 0 层：/data/acg/file.jpg
保留 1 层：/data/acg/path1/file.jpg
保留 2 层：/data/acg/path2/path1/file.jpg
```
