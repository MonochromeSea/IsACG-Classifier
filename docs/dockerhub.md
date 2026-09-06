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
| `DOCKERHUB_USERNAME` | Docker Hub 登录用户名，例如 `monomm` |
| `DOCKERHUB_TOKEN` | Docker Hub Access Token |

## 触发构建

工作流文件：

```text
.github/workflows/dockerhub.yml
```

触发方式：

- 推送 `v*` tag，例如 `v0.1.0`

普通文件改动或推送到 `main` 不会构建或推送 Docker Hub 镜像。

## 镜像标签

CPU 镜像：

```text
monomm/isacg-classifier:v0.1.0
```

Vulkan/WebGPU 镜像：

```text
monomm/isacg-classifier-vulkan:v0.1.0
```

Docker Hub tag 与 GitHub tag 保持一致。CPU 和 Vulkan 使用两个 Docker Hub 仓库区分镜像类型，避免同一个 tag 被两个不同镜像互相覆盖。

## 使用预构建镜像

CPU 版本：

```bash
echo "ISACG_VERSION=v0.1.0" > .env
docker compose -f docker-compose.yml -f docker-compose.image.yml up -d
```

Vulkan/WebGPU 版本：

```bash
echo "ISACG_VERSION=v0.1.0" > .env
docker compose -f docker-compose.yml -f docker-compose.vulkan.yml -f docker-compose.image.vulkan.yml up -d
```

如果镜像不在 `monomm/isacg-classifier`，在 `.env` 中覆盖完整镜像名：

```dotenv
ISACG_IMAGE=your-dockerhub-name/isacg-classifier:v0.1.0
```

Vulkan 版则使用：

```dotenv
ISACG_IMAGE=your-dockerhub-name/isacg-classifier-vulkan:v0.1.0
```
