# GPT-Engineer Web接口 API文档

本文档详细说明了GPT-Engineer Web界面提供的API接口，包括REST API和WebSocket通信。

## 基本信息

- **基础URL**: `http://localhost:8000`
- **API版本**: v1
- **内容类型**: `application/json`

## REST API

### 1. 创建项目

创建一个新的代码生成项目。

**请求**:

```
POST /api/projects
```

**请求体**:

```json
{
  "prompt": "项目需求描述",
  "model": "gpt-4",
  "temperature": 0.1
}
```

**参数说明**:

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|--------|------|------|--------|------|
| prompt | string | 是 | - | 项目需求描述 |
| model | string | 否 | "gpt-4" | 使用的AI模型 |
| temperature | float | 否 | 0.1 | 生成代码的创造性程度(0.0-1.0) |

**响应**:

```json
{
  "project_id": "d677bf0f-1fc9-4ce7-8f2e-d94bb1a68df2"
}
```

**状态码**:

- `200 OK`: 请求成功
- `400 Bad Request`: 请求参数错误
- `500 Internal Server Error`: 服务器内部错误

### 2. 获取项目信息

获取指定项目的详细信息，包括生成的文件。

**请求**:

```
GET /api/projects/{project_id}
```

**路径参数**:

| 参数名 | 类型 | 描述 |
|--------|------|------|
| project_id | string | 项目ID |

**响应**:

```json
{
  "id": "d677bf0f-1fc9-4ce7-8f2e-d94bb1a68df2",
  "prompt": "项目需求描述",
  "files": [
    {
      "name": "main.py",
      "content": "print('Hello World')"
    },
    {
      "name": "requirements.txt",
      "content": "flask==2.0.1"
    }
  ]
}
```

**状态码**:

- `200 OK`: 请求成功
- `404 Not Found`: 项目不存在
- `500 Internal Server Error`: 服务器内部错误

### 3. 获取首页

获取Web界面的HTML页面。

**请求**:

```
GET /
```

**响应**:

返回HTML页面。

**状态码**:

- `200 OK`: 请求成功

### 4. 获取项目页面

获取项目详情页面。

**请求**:

```
GET /project/{project_id}
```

**路径参数**:

| 参数名 | 类型 | 描述 |
|--------|------|------|
| project_id | string | 项目ID |

**响应**:

返回HTML页面。

**状态码**:

- `200 OK`: 请求成功

### 5. 获取项目信息

获取项目的基本信息。

**请求**:

```
GET /api/project/{project_id}
```

**参数说明**:

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|--------|------|------|--------|------|
| project_id | string | 是 | - | 项目ID |

**响应**:

```json
{
  "project_id": "test-project",
  "exists": true,
  "file_count": 10
}
```

**状态码**:

- `200`: 请求成功
- `404`: 项目不存在
- `500`: 服务器错误

### 6. 获取项目文件列表

获取项目下的所有文件列表。

**请求**:

```
GET /api/project/{project_id}/files
```

**参数说明**:

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|--------|------|------|--------|------|
| project_id | string | 是 | - | 项目ID |

**响应**:

```json
{
  "project_id": "test-project",
  "files": [
    {
      "path": "main.py",
      "size": 1024,
      "modified": 1647583267.0
    },
    {
      "path": "utils/helpers.py",
      "size": 512,
      "modified": 1647583200.0
    }
  ]
}
```

**状态码**:

- `200`: 请求成功
- `404`: 项目不存在
- `500`: 服务器错误

### 7. 获取文件内容

获取项目中指定文件的内容。

**请求**:

```
GET /api/project/{project_id}/file?file_path={file_path}
```

**参数说明**:

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|--------|------|------|--------|------|
| project_id | string | 是 | - | 项目ID |
| file_path | string | 是 | - | 文件路径，相对于项目根目录 |

**响应**:

```json
{
  "project_id": "test-project",
  "file_path": "main.py",
  "content": "print('Hello, World!')"
}
```

或者对于二进制文件：

```json
{
  "project_id": "test-project",
  "file_path": "image.png",
  "content": "[二进制文件，无法显示内容]",
  "is_binary": true
}
```

**状态码**:

- `200`: 请求成功
- `404`: 项目或文件不存在
- `500`: 服务器错误

### 8. 更新文件内容

修改并保存项目中指定文件的内容。

**请求**:

```
POST /api/project/{project_id}/file?file_path={file_path}
```

**请求体**:

```json
{
  "content": "print('Hello, Updated World!')"
}
```

**参数说明**:

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|--------|------|------|--------|------|
| project_id | string | 是 | - | 项目ID |
| file_path | string | 是 | - | 文件路径，相对于项目根目录 |
| content | string | 是 | - | 新的文件内容 |

**响应**:

```json
{
  "project_id": "test-project",
  "file_path": "main.py",
  "status": "success",
  "message": "文件内容已更新"
}
```

**状态码**:

- `200`: 请求成功
- `404`: 项目不存在
- `500`: 服务器错误

### 9. 删除文件

删除项目中指定的文件。

**请求**:

```
DELETE /api/project/{project_id}/file?file_path={file_path}
```

**参数说明**:

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|--------|------|------|--------|------|
| project_id | string | 是 | - | 项目ID |
| file_path | string | 是 | - | 文件路径，相对于项目根目录 |

**响应**:

```json
{
  "project_id": "test-project",
  "file_path": "main.py",
  "status": "success",
  "message": "文件已删除"
}
```

**状态码**:

- `200`: 请求成功
- `404`: 项目或文件不存在
- `500`: 服务器错误

## WebSocket API

WebSocket接口用于实时接收代码生成过程的消息。

### 连接WebSocket

**URL**:

```
ws://localhost:8000/ws/{project_id}
```

**路径参数**:

| 参数名 | 类型 | 描述 |
|--------|------|------|
| project_id | string | 项目ID |

### 消息类型

WebSocket通信中的消息格式为JSON，包含以下类型：

#### 1. 状态消息

```json
{
  "type": "status",
  "status": "connected|processing|completed|failed",
  "message": "状态描述信息"
}
```

**字段说明**:

- `type`: 消息类型，固定为 "status"
- `status`: 状态值，可能的值包括：
  - `connected`: WebSocket连接已建立
  - `processing`: 代码生成中
  - `completed`: 代码生成完成
  - `failed`: 代码生成失败
- `message`: 状态描述信息

#### 2. 提示消息

```json
{
  "type": "prompt",
  "prompt": "项目需求描述"
}
```

**字段说明**:

- `type`: 消息类型，固定为 "prompt"
- `prompt`: 项目需求描述

#### 3. 步骤消息

```json
{
  "type": "message",
  "step": "步骤名称",
  "content": "步骤内容"
}
```

**字段说明**:

- `type`: 消息类型，固定为 "message"
- `step`: 步骤名称，如 "gen_code"
- `content`: 步骤内容，通常是AI生成的文本

#### 4. 完成消息

```json
{
  "type": "complete",
  "files": [
    {
      "name": "文件名",
      "content": "文件内容"
    }
  ]
}
```

**字段说明**:

- `type`: 消息类型，固定为 "complete"
- `files`: 生成的文件列表，每个文件包含名称和内容

#### 5. 错误消息

```json
{
  "type": "error",
  "message": "错误信息"
}
```

**字段说明**:

- `type`: 消息类型，固定为 "error"
- `message`: 错误信息

## 使用示例

### 创建项目并接收实时更新

1. 发送POST请求创建项目：

```javascript
const response = await fetch('/api/projects', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    prompt: '创建一个简单的待办事项应用程序',
    model: 'gpt-4',
    temperature: 0.1
  })
});

const data = await response.json();
const projectId = data.project_id;
```

2. 连接WebSocket接收实时更新：

```javascript
const socket = new WebSocket(`ws://localhost:8000/ws/${projectId}`);

socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case 'status':
      console.log(`状态更新: ${data.status} - ${data.message}`);
      break;
    case 'message':
      console.log(`步骤: ${data.step}`);
      console.log(`内容: ${data.content}`);
      break;
    case 'complete':
      console.log(`生成完成，文件数: ${data.files.length}`);
      break;
    case 'error':
      console.error(`错误: ${data.message}`);
      break;
  }
};
```

## 错误处理

API可能返回以下错误：

- `400 Bad Request`: 请求参数无效
- `404 Not Found`: 请求的资源不存在
- `500 Internal Server Error`: 服务器内部错误

WebSocket连接可能发送错误消息：

```json
{
  "type": "error",
  "message": "错误信息"
}
```

## 注意事项

1. API密钥安全：确保您的OpenAI API密钥安全，不要在客户端代码中暴露它。

2. 资源限制：代码生成过程可能需要较长时间，取决于项目复杂度和OpenAI API的响应速度。

3. 文件存储：生成的代码文件存储在服务器的`web_projects`目录中，每个项目有一个唯一的ID作为子目录。

4. 并发限制：根据您的OpenAI API计划，可能存在API调用频率限制。 
