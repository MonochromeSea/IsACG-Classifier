# IsACG 图片风格分类器

这是一个基于 [IsACG](https://github.com/moyanj/IsACG) 模型的网页图片分类器。项目按 Docker 部署设计，使用 ONNX Runtime 进行推理，不依赖 PyTorch 和 Gradio。

## 功能

- 判断图片是否为 ACG、二次元、漫画或游戏风格
- 支持拖拽上传和批量上传，一次最多 40 张
- 支持切换 v1、v1s、v2 三个模型
- 支持按分类结果把图片移动到 `storage/acg` 或 `storage/non_acg`
- 支持选择服务器文件夹，递归扫描并批量识别
- 支持按原路径层级整理到 ACG / 非 ACG 文件夹
- 支持移动、复制、硬链接、软链接四种文件处理方式
- 支持监控源文件夹新增文件并自动识别移动
- 支持设置识别线程数
- 批量扫描、识别、移动显示实时进度和运行日志
- 批量识别完成一张立即按结果处理一张，不必等待全部图片识别结束
- 支持撤销当前批量任务的移动结果
- 自动监控可独立设置识别后是否自动移动
- 任务支持暂停、继续、取消，并在刷新或异常关闭后恢复
- 网页自适应手机和电脑屏幕

浏览器打开 <http://localhost:8080>。

分类完成后，可以单张移动，也可以点击“按结果移动全部”。移动后的文件默认位于：

```text
storage/
├── inbox/        # 分类后待移动的图片
├── acg/          # 被判定为 ACG 风格的图片
└── non_acg/      # 被判定为非 ACG 风格的图片
```

也可以通过环境变量 `STORAGE_DIR` 指定其他存储目录。

## 文件夹识别与自动监控

打开 <http://localhost:8080/settings> 进入文件夹识别与设置页。

1. 选择“源文件夹”，并分别选择 ACG 输出文件夹和非 ACG 输出文件夹。
2. 设置识别线程数、是否递归扫描、是否自动移动。
3. 点击“扫描图片”，再点击“开始批量识别”。
4. 如需要后台自动处理新增文件，点击“启动监控”。

批量任务会在每张图片识别完成后立即处理该图片。任务结果中的“撤销移动”可以恢复移动模式的源文件，或删除复制、硬链接、软链接创建的目标文件。

移动文件时会保留原文件名。可以通过“保留路径层数”决定保留多少层父目录：

```text
原路径：源文件夹/path3/path2/path1/file.jpg

保留 0 层：ACG 输出文件夹/file.jpg
保留 1 层：ACG 输出文件夹/path1/file.jpg
保留 2 层：ACG 输出文件夹/path2/path1/file.jpg
```

在 Docker 中运行时，需要把服务器上的源文件夹和输出文件夹挂载进容器，并使用容器内路径在网页中选择。

## Docker 快速开始

最小 `docker-compose.yml` 示例：

```yaml
services:
  isacg:
    image: monomm/isacg-classifier:latest
    container_name: isacg-classifier
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      HOST: 0.0.0.0
      PORT: "8080"
      STORAGE_DIR: /app/storage
      ISACG_DEVICE: CPU
      ISACG_PRELOAD_MODELS: v1s
      ORT_INTRA_OP_THREADS: "1"
      ORT_INTER_OP_THREADS: "1"
      WAITRESS_THREADS: "4"
      JOB_SAVE_INTERVAL: "0.75"
      JOB_HISTORY_LIMIT: "30"
    volumes:
      - ./storage:/app/storage
      - ./config:/app/config
      - /path/to/source:/data/source
      - /path/to/acg:/data/acg
      - /path/to/non_acg:/data/non_acg
```

保存后启动：

```bash
docker compose up -d
docker compose logs -f isacg
```

如果从源码构建，使用仓库内置 compose 文件：

复制配置文件：

```bash
cp .env.example .env
```

编辑 `.env`，把宿主机图片目录改成自己的路径：

```dotenv
ISACG_SOURCE_DIR=/path/to/source
ISACG_ACG_DIR=/path/to/acg
ISACG_NON_ACG_DIR=/path/to/non_acg
```

启动 CPU 版本：

```bash
docker compose up -d --build
docker compose logs -f isacg
```

如果 NAS 的 Docker Hub 镜像源返回 `401 Unauthorized`，保持 `.env` 中的 `PYTHON_SLIM_IMAGE=docker.m.daocloud.io/library/python:3.12-slim-bookworm`。CPU 和 Vulkan 构建都会使用这个基础镜像变量。

如果使用 Docker Hub 预构建镜像：

```bash
docker compose -f docker-compose.yml -f docker-compose.image.yml up -d
```

启动 Vulkan/WebGPU 版本：

```bash
docker compose -f docker-compose.yml -f docker-compose.vulkan.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.vulkan.yml logs -f isacg
```

使用 Docker Hub 预构建 Vulkan 镜像：

```bash
docker compose -f docker-compose.yml -f docker-compose.vulkan.yml -f docker-compose.image.vulkan.yml up -d
```

Vulkan/WebGPU 版属于实验性加速路径。日志显示 `WebGPUExecutionProvider/Vulkan` 代表模型走了 WebGPU/Vulkan EP，但不保证一定使用真实核显；如果容器没有拿到 `/dev/dri` 或驱动回落到 Mesa 软件 Vulkan，可能比 CPU 版更慢。建议用同一批图片对比单张耗时后再决定是否长期使用。

容器内对应路径固定为：

```text
/data/source
/data/acg
/data/non_acg
```

网页设置页中请填写容器内路径，而不是宿主机路径。

更多部署细节见 [docs/docker.md](docs/docker.md)，Docker Hub 自动构建见 [docs/dockerhub.md](docs/dockerhub.md)，环境变量说明见 [docs/configuration.md](docs/configuration.md)，Vulkan 和 Docker 常见问题见 [docs/troubleshooting.md](docs/troubleshooting.md)。

## 运行优化

Docker 默认只预加载 `v1s`，`v1` 和 `v2` 会在第一次使用时加载，以减少启动时间和常驻内存。若希望三个模型启动后都立即可用，可在 `.env` 设置：

```dotenv
ISACG_PRELOAD_MODELS=v1s,v1,v2
```

NAS 或低功耗主机建议保持：

```dotenv
ORT_INTRA_OP_THREADS=1
ORT_INTER_OP_THREADS=1
```

再通过网页中的“识别线程数”控制并发。任务状态会按间隔合并写入 `config/jobs.json`，并默认只保留最近 30 个任务，减少频繁小文件写入和历史文件膨胀。

## 模型文件

模型放在 `models/` 目录，默认使用 `v1s`。

| 模型 | 文件 | 说明 |
| --- | --- | --- |
| v1s | `IsACG_v1s_98.94%.onnx` | 轻量，推荐 |
| v1 | `IsACG_v1_99.06%.onnx` | 高精度 |
| v2 | `IsACG_v2_97.53%.onnx` | 泛化改进 |

## 开源说明

本项目使用 IsACG 模型文件。IsACG 使用 MIT License，随仓库分发模型或相关材料时需要保留上游版权声明和许可证文本。

模型来源说明见 [NOTICE.md](NOTICE.md) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。贡献说明见 [CONTRIBUTING.md](CONTRIBUTING.md)，安全说明见 [SECURITY.md](SECURITY.md)，变更记录见 [CHANGELOG.md](CHANGELOG.md)。
