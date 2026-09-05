# Docker Hub 自动构建

本项目可以通过 GitHub Actions 自动构建并推送 Docker Hub 镜像。

## 准备 Docker Hub Token

在 Docker Hub 创建 Access Token，然后到 GitHub 仓库设置：

```text
Settings -> Secrets and variables -> Actions -> Repository secrets
```

新增两个 secret：

| Secret | 说明 |
| --- | --- |
| `DOCKERHUB_USERNAME` | Docker Hub 用户名，例如 `monomm` |
| `DOCKERHUB_TOKEN` | Docker Hub Access Token |

## 触发构建

工作流文件：

```text
.github/workflows/dockerhub.yml
```

触发方式：

- 推送到 `main`
- 推送 `v*` tag，例如 `v0.1.0`
- 在 GitHub Actions 页面手动运行

## 镜像标签

CPU 镜像：

```text
DOCKERHUB_USERNAME/isacg-classifier:latest
DOCKERHUB_USERNAME/isacg-classifier:cpu
DOCKERHUB_USERNAME/isacg-classifier:cpu-<git-sha>
DOCKERHUB_USERNAME/isacg-classifier:v0.1.0
```

Vulkan/WebGPU 镜像：

```text
DOCKERHUB_USERNAME/isacg-classifier:vulkan
DOCKERHUB_USERNAME/isacg-classifier:vulkan-<git-sha>
DOCKERHUB_USERNAME/isacg-classifier:v0.1.0-vulkan
```

## 使用预构建镜像

CPU 版本：

```bash
docker compose -f docker-compose.yml -f docker-compose.image.yml up -d
```

Vulkan/WebGPU 版本：

```bash
docker compose -f docker-compose.yml -f docker-compose.vulkan.yml -f docker-compose.image.vulkan.yml up -d
```

如果镜像不在 `monomm/isacg-classifier`，在 `.env` 中覆盖：

```dotenv
ISACG_IMAGE=your-dockerhub-name/isacg-classifier:latest
```

Vulkan 版则使用：

```dotenv
ISACG_IMAGE=your-dockerhub-name/isacg-classifier:vulkan
```
