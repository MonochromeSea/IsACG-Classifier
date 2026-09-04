# IsACG 图片风格分类器

这是一个基于 [IsACG](https://github.com/moyanj/IsACG) 模型的网页图片分类器。它使用 ONNX Runtime 进行推理，不依赖 PyTorch 和 Gradio，适合在 Windows 上调试，也适合部署到飞牛 NAS 等 Linux 环境。

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
- 自动监控可独立设置识别后是否自动移动
- 网页自适应手机和电脑屏幕

## Windows 本地运行

1. 安装 Python 3.10 或更高版本。
2. 在项目目录安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

3. 启动服务：

```powershell
python app.py
```

4. 浏览器打开 <http://localhost:8080>。

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

移动文件时会保留原文件名。可以通过“保留路径层数”决定保留多少层父目录：

```text
原路径：源文件夹/path3/path2/path1/file.jpg

保留 0 层：ACG 输出文件夹/file.jpg
保留 1 层：ACG 输出文件夹/path1/file.jpg
保留 2 层：ACG 输出文件夹/path2/path1/file.jpg
```

在 Docker 中运行时，需要把服务器上的源文件夹和输出文件夹挂载进容器，并使用容器内路径在网页中选择。

## 飞牛 NAS 部署

飞牛通常提供 Docker 或 Python 运行环境，推荐使用 Docker。

### 方式一：Docker

推荐使用 Docker Compose：

```bash
docker compose up -d --build
```

也可以直接执行：

```bash
./start_docker.sh
```

容器内需要访问飞牛上的图片目录。请编辑 `docker-compose.yml`，把宿主机目录挂载到容器内路径，例如：

```yaml
volumes:
  - ./storage:/app/storage
  - ./config:/app/config
  - /vol1/images:/data/source
  - /vol1/acg:/data/acg
  - /vol1/non_acg:/data/non_acg
```

启动后，在网页设置页里填写容器内路径：

```text
源文件夹：/data/source
ACG 输出文件夹：/data/acg
非 ACG 输出文件夹：/data/non_acg
```

### 方式二：直接运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

如果希望稳定运行，建议直接使用：

```bash
./start_fnos.sh
```

脚本会自动创建虚拟环境、安装依赖，并用 waitress 启动服务。

## 模型文件

模型放在 `models/` 目录，默认使用 `v1s`。

| 模型 | 文件 | 说明 |
| --- | --- | --- |
| v1s | `IsACG_v1s_98.94%.onnx` | 轻量，推荐 |
| v1 | `IsACG_v1_99.06%.onnx` | 高精度 |
| v2 | `IsACG_v2_97.53%.onnx` | 泛化改进 |
