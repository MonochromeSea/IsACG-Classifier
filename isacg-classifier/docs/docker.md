# Docker 部署

本项目以 Docker 部署为主，保留两个运行入口：

- CPU 最小镜像：依赖少、构建快、兼容性最好
- Vulkan/WebGPU 镜像：适合具备 Vulkan 驱动和 `/dev/dri` 设备的 Linux 主机

## CPU 版本

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f isacg
```

停止：

```bash
docker compose down
```

无缓存重建：

```bash
docker compose build --no-cache isacg
docker compose up -d
```

## Vulkan/WebGPU 版本

Vulkan 版本使用 ONNX Runtime WebGPU Execution Provider 插件。在 Linux 下，WebGPU 通过 Dawn 使用 Vulkan 后端。

启动：

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.vulkan.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.vulkan.yml logs -f isacg
```

成功时日志应出现：

```text
已注册 WebGPU/Vulkan 插件：WebGpuExecutionProvider
模型 v1s 使用推理后端：WebGPUExecutionProvider/Vulkan
```

切回 CPU 版本：

```bash
docker compose -f docker-compose.yml -f docker-compose.vulkan.yml down
docker compose up -d --build
```

## 目录映射

`.env` 中填写宿主机路径：

```dotenv
ISACG_SOURCE_DIR=/path/to/source
ISACG_ACG_DIR=/path/to/acg
ISACG_NON_ACG_DIR=/path/to/non_acg
```

容器内固定路径：

```text
/data/source
/data/acg
/data/non_acg
```

网页设置页里请填写容器内路径，而不是宿主机路径。

## 镜像源

Vulkan 镜像默认使用可覆盖的 Python 基础镜像：

```dotenv
PYTHON_SLIM_IMAGE=docker.m.daocloud.io/library/python:3.12-slim-bookworm
```

如果当前网络可以直连 Docker Hub，可以改为：

```dotenv
PYTHON_SLIM_IMAGE=python:3.12-slim-bookworm
```

CPU 版本可在 `docker-compose.yml` 的 `BASE_IMAGE` 构建参数中调整基础镜像。
