# Docker 部署

本项目以 Docker 部署为主，保留两个运行入口：

- CPU 最小镜像：依赖少、构建快、兼容性最好
- Vulkan/WebGPU 镜像：实验性加速路径，适合具备 Vulkan 驱动和 `/dev/dri` 设备的 Linux 主机

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

注意：`WebGPUExecutionProvider/Vulkan` 只说明模型走了 WebGPU/Vulkan EP，不一定说明真实核显正在参与计算。如果容器没有映射 `/dev/dri`，或 Vulkan 驱动回落到 Mesa 软件实现，实际速度可能比 CPU 版本更慢。

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

检查 compose 是否映射核显设备：

```bash
docker compose -f docker-compose.yml -f docker-compose.vulkan.yml config | grep -A3 devices
docker inspect isacg-classifier --format '{{json .HostConfig.Devices}} {{json .HostConfig.Privileged}} {{json .HostConfig.GroupAdd}}'
```

默认不需要 `privileged: true`。通常只要映射 `/dev/dri`，并通过 `group_add` 给到 render 设备权限即可。

如果要确认 Vulkan 设备名，可以临时进入容器安装诊断工具：

```bash
docker exec -it isacg-classifier sh
apt-get update && apt-get install -y --no-install-recommends vulkan-tools
vulkaninfo --summary
```

如果设备名出现 `llvmpipe` 或 `lavapipe`，说明是软件 Vulkan，不是真实 GPU 加速。

如果容器同时看到真实 GPU 和 `llvmpipe`，可以在 `.env` 中强制选择真实 GPU。值来自 `vulkaninfo --summary` 输出里的 `vendorID:deviceID`：

```dotenv
MESA_VK_DEVICE_SELECT=8086:3e96!
```

末尾的 `!` 表示只向 Vulkan 应用暴露这个设备。上面这个值对应 Intel UHD Graphics P630。

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

CPU 和 Vulkan 版本都会读取 `PYTHON_SLIM_IMAGE`。如果构建 CPU 版时遇到 `docker.fnnas.com` 返回 `401 Unauthorized`，保持 `.env.example` 里的 DaoCloud 镜像源即可。
