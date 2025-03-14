# WebSocket API 故障排除指南

本文档提供了使用WebSocket API代码生成功能时可能遇到的常见问题及其解决方案。

## 环境设置问题

### 1. OpenAI API 错误

**问题**: 启动服务器时出现以下错误：

```
AttributeError: module 'openai' has no attribute 'RateLimitError'
```

**解决方案**:

这是因为你使用的是新版本的 OpenAI SDK（>=1.0.0），而代码是为旧版本编写的。我们已经修复了这个问题，但如果你仍然遇到类似错误，可以尝试以下解决方案：

1. 降级 OpenAI SDK 到旧版本：

```bash
pip install openai==0.28.0
```

2. 或者更新代码以适应新版本的 OpenAI SDK，修改 `gpt_engineer/core/ai.py` 文件中的错误处理部分。

### 2. API 密钥未设置

**问题**: 连接到WebSocket后收到警告消息：

```
警告: 未设置OPENAI_API_KEY环境变量，代码生成功能可能无法正常工作
```

**解决方案**:

1. 确保在 `.env` 文件中正确设置了 `OPENAI_API_KEY`：

```
OPENAI_API_KEY=sk-your-actual-api-key
```

2. 重启服务器以加载新的环境变量。

### 3. 依赖安装问题

**问题**: 启动服务器时出现模块导入错误。

**解决方案**:

确保安装了所有必要的依赖：

```bash
pip install fastapi uvicorn websockets openai langchain langchain_openai python-dotenv
```

## 连接问题

### 1. 无法连接到WebSocket服务器

**问题**: 前端无法连接到WebSocket服务器。

**解决方案**:

1. 确保服务器正在运行：

```bash
python web_server.py
```

2. 检查连接URL是否正确，默认为：

```
ws://localhost:8000/ws/{project_id}
```

3. 检查浏览器控制台是否有错误消息。

4. 确保没有防火墙阻止WebSocket连接。

### 2. 连接断开

**问题**: WebSocket连接频繁断开。

**解决方案**:

1. 检查网络连接稳定性。
2. 增加WebSocket心跳检测。
3. 实现自动重连机制。

## 代码生成问题

### 1. 代码生成超时

**问题**: 代码生成请求长时间没有响应。

**解决方案**:

1. 简化你的请求，使其更加具体和简洁。
2. 检查API密钥是否有足够的配额。
3. 检查服务器日志以获取更多信息。

### 2. 生成的代码质量问题

**问题**: 生成的代码不符合预期或有错误。

**解决方案**:

1. 提供更详细和具体的描述。
2. 尝试调整模型参数，如降低温度值（`TEMPERATURE=0.1`）以获得更确定性的结果。
3. 对于复杂的项目，考虑分步骤生成代码。

### 3. 文件保存错误

**问题**: 代码生成成功但文件保存失败。

**解决方案**:

1. 检查项目目录的写入权限。
2. 确保文件路径不包含非法字符。
3. 检查磁盘空间是否充足。

## 其他问题

### 1. 性能问题

**问题**: 服务器响应缓慢。

**解决方案**:

1. 增加服务器资源（CPU、内存）。
2. 优化代码生成流程。
3. 考虑使用异步任务队列处理代码生成请求。

### 2. 日志问题

**问题**: 无法获取足够的调试信息。

**解决方案**:

1. 增加日志级别：

```
LOG_LEVEL=DEBUG
```

2. 检查日志文件以获取详细信息。

## 获取帮助

如果你遇到的问题无法通过本指南解决，请尝试以下方式获取帮助：

1. 查看详细的API文档。
2. 检查服务器日志以获取更多信息。
3. 提交GitHub Issue，并提供详细的错误信息和复现步骤。 
