# 故障排查

## Vulkan 容器启动后仍然走 CPU

确认容器是否拿到核显设备：

```bash
docker inspect isacg-classifier --format '{{json .HostConfig.Devices}}'
docker exec -it isacg-classifier sh -lc 'ls -l /dev/dri'
```

确认 ONNX Runtime 可用 provider：

```bash
docker exec -it isacg-classifier python3 -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

如果只看到：

```text
['AzureExecutionProvider', 'CPUExecutionProvider']
```

说明 WebGPU EP 插件没有安装成功、没有被注册，或当前容器不是 Vulkan 镜像。建议强制重建：

```bash
docker compose -f docker-compose.yml -f docker-compose.vulkan.yml down
docker compose -f docker-compose.yml -f docker-compose.vulkan.yml up -d --build --force-recreate
```

## `/dev/dri` 权限

查看 render 设备组 ID：

```bash
ls -ln /dev/dri
```

如果 `renderD128` 的组 ID 不是 `0`，在 `.env` 中设置：

```dotenv
ISACG_RENDER_GID=109
```

把 `109` 替换为宿主机实际 GID 后重新创建容器。

## `XDG_RUNTIME_DIR is invalid or not set`

Vulkan/WebGPU 运行时可能需要 `XDG_RUNTIME_DIR`。Vulkan compose 已设置：

```dotenv
XDG_RUNTIME_DIR=/tmp/runtime-root
```

若仍有警告，检查容器内目录：

```bash
docker exec -it isacg-classifier sh -lc 'ls -ld /tmp/runtime-root'
```

## `Vulkan shaderUniform*ArrayDynamicIndexing required`

这是 Dawn/Vulkan 对 GPU 能力的提示。只要后续日志显示：

```text
模型 v1s 使用推理后端：WebGPUExecutionProvider/Vulkan
```

通常可以继续使用。若随后回落 CPU 或容器退出，说明当前 GPU/驱动组合不满足 WebGPU EP 要求，建议升级 Mesa/厂商驱动，或使用 CPU 镜像。

## 容器退出码 137

退出码 `137` 常见原因是内存不足。

建议：

- 保持 `ISACG_PRELOAD_MODELS=v1s`
- 降低网页设置页中的识别线程数
- 保持 `ORT_INTRA_OP_THREADS=1` 和 `ORT_INTER_OP_THREADS=1`
- 提高容器内存限制
- 先使用 CPU 版本确认功能，再切换 Vulkan 版本

## 拉取基础镜像 401 或超时

如果构建时看到 Docker Hub 镜像源 `401 Unauthorized` 或超时，可以在 `.env` 中换一个可访问的基础镜像源：

```dotenv
PYTHON_SLIM_IMAGE=docker.m.daocloud.io/library/python:3.12-slim-bookworm
```

保存后重新构建。

## pip 找不到 `onnxruntime-ep-webgpu`

Vulkan 版本依赖 `onnxruntime-ep-webgpu`。如果当前 pip 源不可用，先升级 pip 或换可访问的 PyPI 镜像源后重试。

```bash
python3 -m pip install --upgrade pip
```

如果目标架构没有对应 wheel，Vulkan 版本无法直接通过 pip 安装，需要换到受支持的架构，或使用 CPU 镜像。

## 如何判断 GPU 是否工作

部分 NAS 管理界面不会显示 WebGPU/Vulkan 任务的 GPU 占用。建议综合判断：

- 应用日志是否显示 `WebGPUExecutionProvider/Vulkan`
- 单张图片的 `elapsed_ms` 是否明显降低
- `docker exec` 中 provider 是否包含 WebGPU 插件
- 宿主机可用时，用 `intel_gpu_top`、`radeontop` 或 `nvtop` 观察
