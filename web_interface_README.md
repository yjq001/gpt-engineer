# GPT-Engineer Web界面

基于GPT-Engineer的Web界面，允许用户通过浏览器输入需求描述，实时观看AI生成代码的过程。

## 功能特点

- 🌐 **Web界面**：通过浏览器访问，无需命令行操作
- ⚡ **实时反馈**：使用WebSocket实时显示代码生成过程
- 📝 **代码高亮**：支持多种编程语言的语法高亮
- 📂 **文件浏览**：方便查看和浏览生成的所有代码文件
- 🔄 **多模型支持**：支持GPT-4和GPT-3.5 Turbo等多种模型
- 🎛️ **参数调整**：可调整温度等生成参数

## 安装

### 前提条件

- Python 3.8+
- OpenAI API密钥

### 安装步骤

1. 克隆GPT-Engineer仓库：

```bash
git clone https://github.com/yjq001/gpt-engineer.git
cd gpt-engineer
```

2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 创建`.env`文件并添加OpenAI API密钥：

```
OPENAI_API_KEY=your_openai_api_key_here
```

## 使用方法

### 启动服务器

```bash
python web_server.py
```

服务器将在`http://localhost:8000`上运行。

### 访问Web界面

1. 打开浏览器，访问`http://localhost:8000`
2. 在表单中输入您的需求描述
3. 选择AI模型和温度参数
4. 点击"生成代码"按钮
5. 实时观看代码生成过程
6. 查看和浏览生成的代码文件

## 项目结构

```
.
├── web_server.py          # 主服务器文件
├── frontend/              # 前端文件
│   ├── index.html         # 主HTML页面
│   └── static/            # 静态资源
│       ├── css/           # CSS样式
│       │   └── styles.css # 主样式文件
│       └── js/            # JavaScript文件
│           └── app.js     # 主脚本文件
├── web_projects/          # 生成的项目存储目录
└── api.md                 # API文档
```

## API文档

详细的API文档请参阅[api.md](api.md)文件。

## 故障排除

### 常见问题

1. **无法连接到服务器**
   - 确保服务器正在运行
   - 检查端口8000是否被占用
   - 尝试使用`localhost`而不是`127.0.0.1`

2. **代码生成过程没有显示**
   - 检查浏览器控制台是否有错误
   - 确保WebSocket连接已建立
   - 验证OpenAI API密钥是否有效

3. **生成的代码有错误**
   - 尝试使用更详细的需求描述
   - 调整温度参数（较低的温度通常产生更可靠的代码）
   - 使用GPT-4而不是GPT-3.5 Turbo获得更好的结果

### 日志

服务器日志会显示在终端中，包括HTTP请求和WebSocket连接信息。如果遇到问题，请查看日志以获取更多信息。

## 自定义

### 修改端口

在`web_server.py`文件的最后一行修改端口号：

```python
uvicorn.run("web_server:app", host="0.0.0.0", port=8000, reload=True)
```

### 修改UI

前端文件位于`frontend`目录中，您可以根据需要修改HTML、CSS和JavaScript文件。

## 贡献

欢迎贡献代码、报告问题或提出改进建议。请遵循以下步骤：

1. Fork仓库
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建Pull Request

## 许可证

本项目遵循与GPT-Engineer相同的许可证。

## 致谢

- [GPT-Engineer](https://github.com/gpt-engineer-org/gpt-engineer)项目提供了核心功能
- [FastAPI](https://fastapi.tiangolo.com/)提供了Web服务器框架
- [highlight.js](https://highlightjs.org/)提供了代码高亮功能 
