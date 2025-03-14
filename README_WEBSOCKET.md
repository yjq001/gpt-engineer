# WebSocket API 代码生成功能

本文档介绍如何使用WebSocket API的代码生成功能，该功能允许客户端通过WebSocket连接发送聊天消息，然后根据聊天内容生成代码。

## 功能概述

WebSocket API提供了以下功能：

1. 实时连接：客户端可以与服务器建立持久连接，实现双向通信
2. 代码生成：根据客户端发送的自然语言描述生成相应的代码
3. 项目管理：每个WebSocket连接都与一个特定的项目ID关联，便于管理多个项目
4. 文件查看：可以查看生成的代码文件内容

## 连接URL

WebSocket连接URL格式如下：

```ws://{server_host}:{server_port}/ws/{project_id}
```

其中：
- `server_host`：服务器主机名或IP地址
- `server_port`：服务器端口号
- `project_id`：项目ID，可以是任意字符串，用于标识不同的项目

例如：
```
ws://localhost:8000/ws/my-project-123
```

## 消息格式

所有消息都使用JSON格式进行传输。

### 客户端发送的消息

#### 1. 聊天消息（代码生成请求）

```json
{
  "type": "chat",
  "content": "创建一个简单的Python计算器程序，支持加减乘除操作"
}
```

#### 2. 获取文件内容

```json
{
  "type": "get_file",
  "path": "calculator.py"
}
```

### 服务器发送的消息

#### 1. 连接状态

```json
{
  "type": "status",
  "status": "connected",
  "message": "WebSocket connection established"
}
```

#### 2. 处理状态

```json
{
  "type": "status",
  "status": "processing",
  "message": "正在生成代码，请稍候..."
}
```

#### 3. 项目信息

```json
{
  "type": "project_info",
  "project_id": "my-project-123",
  "files": ["calculator.py", "README.md"]
}
```

#### 4. 代码生成结果

```json
{
  "type": "code_generated",
  "project_id": "my-project-123",
  "files": [
    {
      "path": "calculator.py",
      "content": "# 计算器程序代码..."
    },
    {
      "path": "README.md",
      "content": "# 计算器程序\n\n这是一个简单的计算器程序..."
    }
  ]
}
```

#### 5. 文件内容

```json
{
  "type": "file_content",
  "path": "calculator.py",
  "content": "# 计算器程序代码..."
}
```

#### 6. 错误消息

```json
{
  "type": "error",
  "message": "生成代码时出错: ..."
}
```

## 使用示例

### 使用Web界面

1. 访问 `http://localhost:8000/static/code_generator.html`
2. 输入项目ID并点击"连接"按钮
3. 在聊天输入框中描述你想要生成的代码
4. 点击"发送"按钮
5. 等待代码生成完成
6. 在文件列表中点击文件名查看生成的代码

### 使用Python脚本

可以使用提供的`test_websocket.py`脚本测试WebSocket API：

```bash
python test_websocket.py --server ws://localhost:8000 --project my-project-123 --prompt "创建一个简单的Python计算器程序，支持加减乘除操作"
```

### 使用JavaScript

```javascript
// 创建WebSocket连接
const socket = new WebSocket('ws://localhost:8000/ws/my-project-123');

// 连接打开时的处理
socket.onopen = function(event) {
  console.log('WebSocket连接已建立');
  
  // 发送聊天消息
  const message = {
    type: 'chat',
    content: '创建一个简单的Python计算器程序，支持加减乘除操作'
  };
  socket.send(JSON.stringify(message));
};

// 接收消息的处理
socket.onmessage = function(event) {
  const response = JSON.parse(event.data);
  console.log('收到消息:', response);
  
  // 处理不同类型的消息
  switch(response.type) {
    case 'code_generated':
      console.log('代码生成完成，共', response.files.length, '个文件');
      // 处理生成的代码...
      break;
    case 'error':
      console.error('错误:', response.message);
      break;
    // 处理其他类型的消息...
  }
};

// 错误处理
socket.onerror = function(error) {
  console.error('WebSocket错误:', error);
};

// 连接关闭的处理
socket.onclose = function(event) {
  console.log('WebSocket连接已关闭');
};
```

## 注意事项

1. 代码生成可能需要一些时间，特别是对于复杂的请求
2. 生成的代码会保存在服务器的`projects/{project_id}`目录中
3. 每个项目ID对应一个独立的项目，可以生成多个文件
4. 如果使用相同的项目ID，新生成的代码会覆盖旧的代码

## 环境变量配置

可以通过环境变量配置代码生成器的行为：

- `MODEL_NAME`：使用的AI模型名称，默认为"gpt-4o"
- `TEMPERATURE`：模型温度参数，控制生成的随机性，默认为0.1
- `AZURE_ENDPOINT`：Azure OpenAI服务的端点URL（如果使用Azure）
- `OPENAI_API_KEY`：OpenAI API密钥
- `LOG_LEVEL`：日志级别，可以是DEBUG、INFO、WARNING、ERROR或CRITICAL

## 环境检查

在使用WebSocket API之前，建议运行环境检查脚本，确保所有必要的依赖和设置都正确：

```bash
python check_env.py
```

这个脚本会检查：
- Python版本
- 必要的依赖包
- OpenAI SDK版本和配置
- 环境变量设置
- 项目结构

如果检查发现任何问题，脚本会提供相应的解决建议。

## 故障排除

如果你在使用WebSocket API时遇到问题，请参阅 [故障排除指南](TROUBLESHOOTING.md)，其中包含常见问题的解决方案。

## 贡献

欢迎贡献代码或提出改进建议。请通过 GitHub Issues 或 Pull Requests 提交你的贡献。 
