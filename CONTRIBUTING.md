# 贡献指南

感谢你愿意改进 IsACG 图片风格分类器。

## 开发环境

Windows：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Linux：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

## 提交前检查

```bash
python -m py_compile app.py folder_service.py job_service.py serve.py
node --check static/app.js
node --check static/settings.js
node --check static/theme.js
```

如修改 Docker 文件，请至少确认 CPU 镜像可以构建：

```bash
docker compose build isacg
```

## 代码约定

- 保持 Docker-first 的部署方式
- 不引入 PyTorch、Gradio 等大体积运行依赖
- 批量处理逻辑应考虑 NAS 场景下的内存占用和磁盘写入频率
- 涉及文件移动、删除、覆盖的改动必须保留可恢复或可解释的行为
- 新增环境变量时同步更新 `.env.example` 和 `docs/configuration.md`

## 模型与许可证

本项目使用 IsACG ONNX 模型。提交模型文件、替换模型或修改再分发方式前，请先确认上游许可证和模型权重授权。
