# 故障排查

## Vulkan 显示启用但速度比 CPU 慢

`WebGPUExecutionProvider/Vulkan` 只代表 ONNX Runtime 使用了 WebGPU/Vulkan EP，不保证真实核显正在参与计算。常见原因：

- 容器没有映射 `/dev/dri`
- 容器用户没有权限访问 `/dev/dri/renderD*`
- Vulkan 驱动回落到 Mesa 软件实现，例如 `llvmpipe` 或 `lavapipe`
- 模型较小，WebGPU/Vulkan 的调度和数据拷贝开销超过了加速收益
- 某些算子仍然回落 CPU，导致 CPU/GPU 来回切换

先确认 compose 最终配置里确实有设备映射：

```bash
docker compose -f docker-compose.yml -f docker-compose.vulkan.yml config | grep -A3 devices
docker inspect isacg-classifier --format '{{json .HostConfig.Devices}} {{json .HostConfig.Privileged}} {{json .HostConfig.GroupAdd}}'
```

默认不需要 `privileged: true`。如果 `/dev/dri` 已映射并且 `renderD*` 权限正确，普通设备映射比高权限容器更合适。

再确认 Vulkan 设备不是软件实现。可临时安装诊断工具：

```bash
docker exec -it isacg-classifier sh
apt-get update && apt-get install -y --no-install-recommends vulkan-tools
vulkaninfo --summary
```

如果输出里是 `llvmpipe` 或 `lavapipe`，说明当前 Vulkan 实际跑在 CPU 软件栈上，比 CPU 版慢是正常的。此时建议直接使用 CPU 版本。

如果同时存在真实 GPU 和 `llvmpipe`，可以在 `.env` 中强制选择真实 GPU：

```dotenv
MESA_VK_DEVICE_SELECT=8086:3e96!
```

值来自 `vulkaninfo --summary` 输出里的 `vendorID:deviceID`。末尾的 `!` 表示只向 Vulkan 应用暴露该设备。`8086:3e96!` 对应 Intel UHD Graphics P630。

如果确认是真实 Intel/AMD GPU，但实测仍比 CPU 慢，也建议保留 CPU 版本。这个项目的 ONNX 模型体积较小，CPU 推理开销低，Vulkan/WebGPU 不一定有稳定收益。

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
- 容器内 `vulkaninfo --summary` 是否显示真实 GPU，而不是 `llvmpipe` 或 `lavapipe`
