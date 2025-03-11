// 全局变量
let socket = null;
let projectId = null;
let files = {};  // 改为对象，以文件名为键
let selectedFile = null;
let currentFileTab = null;
let fileHistory = {}; // 存储文件的编辑历史
let currentEditingFile = null; // 当前正在编辑的文件
let isTypingCode = false; // 是否正在"输入"代码
let typingInterval = null; // 用于模拟打字效果的计时器
let currentStep = null; // 当前步骤
let currentMessage = null; // 当前消息元素
let isGenerating = false; // 是否正在生成代码

// DOM元素
const homePage = document.getElementById('home-page');
const projectPage = document.getElementById('project-page');
const promptForm = document.getElementById('prompt-form');
const submitBtn = document.getElementById('submit-btn');
const temperatureInput = document.getElementById('temperature');
const temperatureValue = document.getElementById('temperature-value');
const projectStatus = document.getElementById('project-status');
const projectPromptText = document.getElementById('project-prompt-text');
const conversationContainer = document.getElementById('conversation-container');
const generatingIndicator = document.getElementById('generating-indicator');
const filesList = document.getElementById('files-list');
const codeContainer = document.querySelector('.code-container code');
const homeLink = document.getElementById('home-link');
const backToHomeBtn = document.getElementById('back-to-home');
const codeEditor = document.querySelector('.code-editor-container');
const chatInput = document.getElementById('chat-input');
const sendMessageBtn = document.getElementById('send-message-btn');

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    // 初始化DOM元素
    initializeDOMElements();
    
    // 检查URL是否包含项目ID
    const path = window.location.pathname;
    const match = path.match(/\/project\/([a-f0-9-]+)/);
    
    if (match && match[1]) {
        projectId = match[1];
        showProjectPage();
        loadProject(projectId);
    } else {
        showHomePage();
    }
    
    // 设置事件监听器
    setupEventListeners();
});

// 初始化DOM元素
function initializeDOMElements() {
    // 重新获取所有DOM元素，确保它们已经加载
    const elements = {
        'home-page': homePage,
        'project-page': projectPage,
        'prompt-form': promptForm,
        'submit-btn': submitBtn,
        'temperature': temperatureInput,
        'temperature-value': temperatureValue,
        'project-status': projectStatus,
        'project-prompt-text': projectPromptText,
        'conversation-container': conversationContainer,
        'generating-indicator': generatingIndicator,
        'files-list': filesList,
        'home-link': homeLink,
        'back-to-home': backToHomeBtn,
        'chat-input': chatInput,
        'send-message-btn': sendMessageBtn
    };
    
    // 检查并记录缺失的元素
    for (const [id, element] of Object.entries(elements)) {
        if (!element) {
            console.warn(`DOM元素未找到: #${id}`);
        }
    }
}

// 设置事件监听器
function setupEventListeners() {
    // 表单提交
    promptForm.addEventListener('submit', handleFormSubmit);
    
    // 温度滑块
    temperatureInput.addEventListener('input', () => {
        temperatureValue.textContent = temperatureInput.value;
    });
    
    // 首页链接
    homeLink.addEventListener('click', (e) => {
        e.preventDefault();
        handleBackToHome();
    });
    
    // 返回首页按钮
    backToHomeBtn.addEventListener('click', handleBackToHome);
    
    // 发送消息按钮
    sendMessageBtn.addEventListener('click', handleSendMessage);
    
    // 聊天输入框回车发送
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    });
}

// 处理发送消息
function handleSendMessage() {
    const message = chatInput.value.trim();
    if (!message || isGenerating) return;
    
    // 添加用户消息
    addUserMessage(message);
    
    // 清空输入框
    chatInput.value = '';
    
    // 设置生成状态
    isGenerating = true;
    generatingIndicator.style.display = 'flex';
    sendMessageBtn.disabled = true;
    
    // 添加AI思考消息
    addAIThinkingMessage();
    
    // 发送消息到服务器
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: 'chat',
            message: message
        }));
    } else {
        // 如果WebSocket未连接，重新连接
        connectWebSocket(projectId, () => {
            socket.send(JSON.stringify({
                type: 'chat',
                message: message
            }));
        });
    }
}

// 处理返回首页
function handleBackToHome() {
    if (socket) {
        socket.close();
        socket = null;
    }
    
    // 清除打字效果计时器
    if (typingInterval) {
        clearInterval(typingInterval);
        typingInterval = null;
    }
    
    projectId = null;
    showHomePage();
    history.pushState({}, '', '/');
}

// 处理表单提交
async function handleFormSubmit(e) {
    e.preventDefault();
    
    // 禁用提交按钮
    submitBtn.disabled = true;
    submitBtn.textContent = '处理中...';
    
    try {
        // 获取表单数据
        const formData = {
            prompt: document.getElementById('prompt').value,
            model: document.getElementById('model').value,
            temperature: parseFloat(document.getElementById('temperature').value)
        };
        
        // 发送请求
        const response = await fetch('/api/projects', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });
        
        if (!response.ok) {
            throw new Error('创建项目失败');
        }
        
        const data = await response.json();
        projectId = data.project_id;
        
        // 更新URL
        history.pushState({}, '', `/project/${projectId}`);
        
        // 显示项目页面
        showProjectPage();
        
        // 设置项目信息
        if (projectPromptText) {
            projectPromptText.textContent = formData.prompt;
        }
        
        // 添加用户消息到对话
        addUserMessage(formData.prompt);
        
        // 设置生成状态
        isGenerating = true;
        
        // 添加AI思考消息
        addAIThinkingMessage();
        
        // 连接WebSocket
        connectWebSocket(projectId);
        
    } catch (error) {
        console.error('Error:', error);
        alert('创建项目失败: ' + error.message);
        
        // 重置提交按钮
        submitBtn.disabled = false;
        submitBtn.textContent = '生成代码';
    }
}

// 加载项目
async function loadProject(id) {
    try {
        // 获取项目信息
        const response = await fetch(`/api/projects/${id}`);
        
        if (!response.ok) {
            throw new Error('获取项目信息失败');
        }
        
        const project = await response.json();
        
        // 设置项目信息
        projectPromptText.textContent = project.prompt;
        
        // 添加用户消息到对话
        addUserMessage(project.prompt);
        
        // 如果有文件，加载文件
        if (project.files && project.files.length > 0) {
            // 初始化文件对象
            files = {};
            
            // 加载文件
            project.files.forEach(file => {
                files[file.name] = file.content;
                
                // 初始化文件历史
                if (!fileHistory[file.name]) {
                    fileHistory[file.name] = [{
                        content: file.content,
                        timestamp: new Date().toISOString()
                    }];
                }
            });
            
            // 更新文件标签和树
            updateFileTree();
            
            // 选择第一个文件
            const firstFileName = Object.keys(files)[0];
            if (firstFileName) {
                selectFileByName(firstFileName);
            }
            
            // 添加完成消息
            addAIMessage('代码生成完成，共生成了 ' + project.files.length + ' 个文件。');
        }
        
        // 连接WebSocket
        connectWebSocket(id);
        
    } catch (error) {
        console.error('Error:', error);
        alert('加载项目失败: ' + error.message);
    }
}

// 连接WebSocket
function connectWebSocket(id, callback) {
    // 确定WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${id}`;
    
    console.log('正在连接WebSocket:', wsUrl);
    
    // 创建WebSocket连接
    socket = new WebSocket(wsUrl);
    
    // 连接打开
    socket.onopen = () => {
        console.log('WebSocket连接已建立');
        if (callback && typeof callback === 'function') {
            callback();
        }
    };
    
    // 接收消息
    socket.onmessage = (event) => {
        console.log('收到WebSocket消息:', event.data);
        try {
            const data = JSON.parse(event.data);
            
            // 打印详细的消息内容
            console.group('WebSocket消息详情');
            console.log('消息类型:', data.type);
            
            switch (data.type) {
                case 'status':
                    console.log('状态:', data.status);
                    console.log('消息:', data.message);
                    break;
                case 'token':
                    console.log('步骤:', data.step);
                    console.log('Token:', data.token);
                    console.log('是代码:', data.is_code);
                    break;
                case 'file_update':
                    console.log('文件名:', data.file);
                    console.log('内容长度:', data.content?.length || 0);
                    break;
                case 'step_start':
                    console.log('步骤开始:', data.step);
                    break;
                case 'step_complete':
                    console.log('步骤完成:', data.step);
                    console.log('内容长度:', data.content?.length || 0);
                    break;
                case 'complete':
                    console.log('文件数量:', data.files?.length || 0);
                    if (data.files && data.files.length > 0) {
                        console.log('文件列表:');
                        data.files.forEach(file => {
                            console.log(`- ${file.name} (${file.content.length} 字节)`);
                        });
                    }
                    break;
                case 'error':
                    console.error('错误消息:', data.message);
                    break;
                case 'chat_response':
                    console.log('聊天回复:', data.message);
                    break;
            }
            
            console.groupEnd();
            
            // 处理消息
            handleWebSocketMessage(data);
        } catch (error) {
            console.error('解析WebSocket消息失败:', error, event.data);
        }
    };
    
    // 连接关闭
    socket.onclose = (event) => {
        console.log('WebSocket连接已关闭:', event.code, event.reason);
    };
    
    // 连接错误
    socket.onerror = (error) => {
        console.error('WebSocket错误:', error);
    };
}

// 处理WebSocket消息
function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'status':
            handleStatusMessage(data);
            break;
        case 'token':
            handleTokenMessage(data);
            break;
        case 'file_update':
            handleFileUpdateMessage(data);
            break;
        case 'step_start':
            handleStepStartMessage(data);
            break;
        case 'step_complete':
            handleStepCompleteMessage(data);
            break;
        case 'complete':
            handleCompleteMessage(data);
            break;
        case 'error':
            handleErrorMessage(data);
            break;
        case 'prompt':
            if (projectPromptText) {
                projectPromptText.textContent = data.prompt;
            }
            break;
        case 'chat_response':
            handleChatResponse(data);
            break;
        default:
            console.log('未知消息类型:', data);
    }
}

// 处理聊天回复
function handleChatResponse(data) {
    // 移除思考中的消息
    const thinkingMessage = conversationContainer.querySelector('.ai-message.thinking');
    if (thinkingMessage) {
        conversationContainer.removeChild(thinkingMessage);
    }
    
    // 添加AI消息
    addAIMessage(data.message);
    
    // 重置生成状态
    isGenerating = false;
    generatingIndicator.style.display = 'none';
    sendMessageBtn.disabled = false;
    
    // 如果有代码修改
    if (data.file_updates && data.file_updates.length > 0) {
        data.file_updates.forEach(update => {
            handleFileUpdateMessage({
                file: update.file,
                content: update.content
            });
        });
    }
}

// 处理状态消息
function handleStatusMessage(data) {
    // 更新状态
    updateStatus(data.status);
    
    // 如果是状态变更，添加到对话
    if (data.status === 'processing') {
        addAIMessage('开始生成代码...');
    } else if (data.status === 'completed') {
        addAIMessage('代码生成完成！');
        generatingIndicator.style.display = 'none';
        isGenerating = false;
        sendMessageBtn.disabled = false;
    } else if (data.status === 'failed') {
        addAIMessage('代码生成失败: ' + data.message);
        generatingIndicator.style.display = 'none';
        isGenerating = false;
        sendMessageBtn.disabled = false;
    }
}

// 处理Token消息
function handleTokenMessage(data) {
    console.log('处理Token消息:', data);
    
    // 如果步骤变更，创建新消息
    if (data.step !== currentStep) {
        currentStep = data.step;
        currentMessage = null;
    }
    
    // 如果没有当前消息，创建一个
    if (!currentMessage) {
        currentMessage = addAIStreamingMessage(data.step);
    }
    
    // 添加token到消息
    appendTokenToMessage(currentMessage, data.token, data.is_code);
    
    // 如果是代码，更新当前编辑的文件
    if (data.is_code && currentEditingFile) {
        // 如果当前文件不存在，创建一个
        if (!files[currentEditingFile]) {
            files[currentEditingFile] = '';
            
            // 更新文件标签和树
            updateFileTree();
            
            // 如果当前没有选中文件，选择这个文件
            if (!currentFileTab) {
                selectFileByName(currentEditingFile);
            }
        }
        
        // 添加token到文件内容
        files[currentEditingFile] += data.token;
        
        // 如果当前选中的是这个文件，更新显示
        if (currentFileTab === currentEditingFile) {
            displayFileContent(currentEditingFile);
        }
        
        // 确保代码编辑器显示打字效果
        if (codeEditor) {
            codeEditor.classList.add('typing');
        }
    }
    
    // 滚动到底部
    conversationContainer.scrollTop = conversationContainer.scrollHeight;
}

// 处理文件更新消息
function handleFileUpdateMessage(data) {
    console.log('处理文件更新消息:', data);
    
    const fileName = data.file;
    const newContent = data.content;
    
    // 保存旧内容用于显示差异
    const oldContent = files[fileName] || '';
    
    // 更新文件内容
    files[fileName] = newContent;
    
    // 添加到文件历史
    if (!fileHistory[fileName]) {
        fileHistory[fileName] = [];
    }
    
    fileHistory[fileName].push({
        content: newContent,
        timestamp: new Date().toISOString()
    });
    
    // 设置当前编辑的文件
    currentEditingFile = fileName;
    
    // 更新文件标签和树
    updateFileTree();
    
    // 如果当前没有选中文件，选择这个文件
    if (!currentFileTab) {
        selectFileByName(fileName);
    }
    
    // 如果当前选中的是这个文件，更新显示
    if (currentFileTab === fileName) {
        // 显示差异而不是直接更新
        displayFileDiff(fileName, oldContent, newContent);
    }
    
    // 设置编辑状态
    if (codeEditor) {
        codeEditor.classList.add('typing');
    }
    
    // 添加文件更新消息
    const isNewFile = oldContent === '';
    if (isNewFile) {
        addAIMessage(`创建了新文件 ${fileName}`);
    } else {
        addAIMessage(`更新了文件 ${fileName}`);
    }
}

// 显示文件差异
function displayFileDiff(fileName, oldContent, newContent) {
    // 如果是新文件，直接显示内容
    if (!oldContent) {
        displayFileContent(fileName);
        return;
    }
    
    // 分割内容为行
    const oldLines = oldContent.split('\n');
    const newLines = newContent.split('\n');
    
    // 简单的差异算法
    const diffResult = [];
    let i = 0, j = 0;
    
    // 最大比较行数，防止过长文件导致性能问题
    const maxLines = Math.max(oldLines.length, newLines.length);
    
    while (i < oldLines.length || j < newLines.length) {
        if (i >= oldLines.length) {
            // 旧文件已结束，新文件还有行
            diffResult.push({ type: 'add', content: newLines[j] });
            j++;
        } else if (j >= newLines.length) {
            // 新文件已结束，旧文件还有行
            diffResult.push({ type: 'remove', content: oldLines[i] });
            i++;
        } else if (oldLines[i] === newLines[j]) {
            // 行相同
            diffResult.push({ type: 'same', content: oldLines[i] });
            i++;
            j++;
        } else {
            // 行不同，尝试查找最近的匹配
            let foundMatch = false;
            
            // 向前查找最多5行
            for (let lookAhead = 1; lookAhead <= 5 && j + lookAhead < newLines.length; lookAhead++) {
                if (oldLines[i] === newLines[j + lookAhead]) {
                    // 找到匹配，添加新行
                    for (let k = 0; k < lookAhead; k++) {
                        diffResult.push({ type: 'add', content: newLines[j + k] });
                    }
                    j += lookAhead;
                    foundMatch = true;
                    break;
                }
            }
            
            if (!foundMatch) {
                // 没找到匹配，认为是删除旧行并添加新行
                diffResult.push({ type: 'remove', content: oldLines[i] });
                diffResult.push({ type: 'add', content: newLines[j] });
                i++;
                j++;
            }
        }
        
        // 防止无限循环
        if (diffResult.length > maxLines * 2) {
            break;
        }
    }
    
    // 生成差异HTML
    let diffHtml = '';
    diffResult.forEach(line => {
        let lineClass = '';
        let prefix = '  ';
        
        if (line.type === 'add') {
            lineClass = 'diff-add';
            prefix = '+ ';
        } else if (line.type === 'remove') {
            lineClass = 'diff-remove';
            prefix = '- ';
        }
        
        diffHtml += `<div class="diff-line ${lineClass}"><span class="diff-prefix">${prefix}</span>${escapeHtml(line.content)}</div>`;
    });
    
    // 显示差异
    const diffContainer = document.createElement('div');
    diffContainer.className = 'diff-container';
    diffContainer.innerHTML = diffHtml;
    
    // 替换代码内容
    const codeContainer = document.querySelector('.code-container');
    const pre = codeContainer.querySelector('pre');
    pre.innerHTML = '';
    pre.appendChild(diffContainer);
    
    // 添加文件名标题
    const fileNameElement = document.createElement('div');
    fileNameElement.className = 'diff-file-name';
    fileNameElement.textContent = fileName;
    pre.insertBefore(fileNameElement, diffContainer);
    
    // 添加按钮切换回正常视图
    const viewNormalButton = document.createElement('button');
    viewNormalButton.className = 'view-normal-btn';
    viewNormalButton.textContent = '查看正常代码';
    viewNormalButton.onclick = () => displayFileContent(fileName);
    pre.insertBefore(viewNormalButton, diffContainer);
}

// 转义HTML特殊字符
function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// 处理步骤开始消息
function handleStepStartMessage(data) {
    currentStep = data.step;
    
    // 添加思考消息
    const thinkingMessage = addAIThinkingMessage();
    thinkingMessage.dataset.step = data.step;
}

// 处理步骤完成消息
function handleStepCompleteMessage(data) {
    // 移除思考中的消息
    const thinkingMessage = conversationContainer.querySelector(`.ai-message.thinking[data-step="${data.step}"]`);
    if (thinkingMessage) {
        conversationContainer.removeChild(thinkingMessage);
    }
    
    // 完成当前消息
    if (currentMessage) {
        currentMessage.classList.remove('streaming');
        currentMessage = null;
    }
    
    // 重置当前步骤
    currentStep = null;
    
    // 重置编辑状态
    currentEditingFile = null;
    if (codeEditor) {
        codeEditor.classList.remove('typing');
    }
    
    // 更新文件标签和树
    updateFileTree();
}

// 更新状态显示
function updateStatus(status) {
    projectStatus.textContent = getStatusText(status);
    projectStatus.className = `status-badge status-${status}`;
}

// 处理完成消息
function handleCompleteMessage(data) {
    // 将文件列表转换为对象
    const filesList = data.files || [];
    
    // 加载文件
    filesList.forEach(file => {
        files[file.name] = file.content;
        
        // 初始化文件历史
        if (!fileHistory[file.name]) {
            fileHistory[file.name] = [{
                content: file.content,
                timestamp: new Date().toISOString()
            }];
        }
    });
    
    // 更新文件标签和树
    updateFileTree();
    
    // 选择第一个文件
    const firstFileName = Object.keys(files)[0];
    if (firstFileName) {
        selectFileByName(firstFileName);
    }
    
    // 添加完成消息
    addAIMessage(`代码生成完成，共生成了 ${filesList.length} 个文件。`);
    
    // 更新状态
    updateStatus('completed');
    
    // 隐藏生成指示器
    generatingIndicator.style.display = 'none';
}

// 处理错误消息
function handleErrorMessage(data) {
    // 添加错误消息
    addAIMessage(`错误: ${data.message}`, 'error');
    
    // 隐藏生成指示器
    generatingIndicator.style.display = 'none';
    
    // 更新状态
    updateStatus('failed');
    
    // 显示错误提示
    const errorTipEl = document.createElement('div');
    errorTipEl.className = 'error-tip';
    
    // 检查是否是API密钥错误
    if (data.message.includes('API') && data.message.includes('密钥')) {
        errorTipEl.innerHTML = `
            <h3>API密钥错误</h3>
            <p>您需要设置有效的OpenAI API密钥才能使用代码生成功能。</p>
            <ol>
                <li>在项目根目录创建或编辑<code>.env</code>文件</li>
                <li>添加以下内容：<code>OPENAI_API_KEY=您的实际API密钥</code></li>
                <li>重启服务器</li>
                <li>刷新页面</li>
            </ol>
            <p>如何获取OpenAI API密钥：<a href="https://platform.openai.com/account/api-keys" target="_blank">访问OpenAI平台</a></p>
        `;
    } else {
        errorTipEl.innerHTML = `
            <h3>发生错误</h3>
            <p>${data.message}</p>
            <p>请检查服务器日志获取更多信息。</p>
        `;
    }
    
    // 添加到最后一条AI消息
    const lastAIMessage = conversationContainer.querySelector('.ai-message:last-child');
    if (lastAIMessage) {
        lastAIMessage.appendChild(errorTipEl);
    }
}

// 添加用户消息
function addUserMessage(content) {
    // 修复：添加null检查
    if (!conversationContainer) return;
    
    const messageEl = document.createElement('div');
    messageEl.className = 'message-bubble user-message';
    
    const contentEl = document.createElement('div');
    contentEl.className = 'message-content';
    contentEl.textContent = content;
    
    messageEl.appendChild(contentEl);
    conversationContainer.appendChild(messageEl);
    
    // 滚动到底部
    conversationContainer.scrollTop = conversationContainer.scrollHeight;
}

// 添加AI思考消息
function addAIThinkingMessage() {
    // 修复：添加null检查
    if (!conversationContainer) return;
    
    const messageEl = document.createElement('div');
    messageEl.className = 'message-bubble ai-message thinking';
    
    const contentEl = document.createElement('div');
    contentEl.className = 'message-content';
    
    const thinkingEl = document.createElement('div');
    thinkingEl.className = 'thinking-dots';
    thinkingEl.innerHTML = '<span>.</span><span>.</span><span>.</span>';
    
    contentEl.appendChild(document.createTextNode('思考中'));
    contentEl.appendChild(thinkingEl);
    
    messageEl.appendChild(contentEl);
    conversationContainer.appendChild(messageEl);
    
    // 滚动到底部
    conversationContainer.scrollTop = conversationContainer.scrollHeight;
    
    return messageEl;
}

// 添加AI流式消息
function addAIStreamingMessage(step) {
    const messageEl = document.createElement('div');
    messageEl.className = 'message-bubble ai-message streaming';
    messageEl.dataset.step = step;
    
    const contentEl = document.createElement('div');
    contentEl.className = 'message-content';
    messageEl.appendChild(contentEl);
    
    conversationContainer.appendChild(messageEl);
    
    // 滚动到底部
    conversationContainer.scrollTop = conversationContainer.scrollHeight;
    
    return messageEl;
}

// 向消息添加token
function appendTokenToMessage(messageEl, token, isCode) {
    if (!messageEl) return;
    
    const contentEl = messageEl.querySelector('.message-content');
    if (!contentEl) return;
    
    // 添加token，无论是否是代码
    contentEl.textContent += token;
    
    // 如果是代码，添加特殊样式
    if (isCode && !messageEl.classList.contains('code-message')) {
        messageEl.classList.add('code-message');
    }
    
    // 滚动到底部
    conversationContainer.scrollTop = conversationContainer.scrollHeight;
}

// 添加AI消息
function addAIMessage(content, type = '') {
    // 移除思考中的消息
    const thinkingMessage = conversationContainer.querySelector('.ai-message.thinking');
    if (thinkingMessage) {
        conversationContainer.removeChild(thinkingMessage);
    }
    
    const messageEl = document.createElement('div');
    messageEl.className = 'message-bubble ai-message';
    
    if (type) {
        messageEl.dataset.type = type;
    }
    
    const contentEl = document.createElement('div');
    contentEl.className = 'message-content';
    contentEl.textContent = content;
    
    messageEl.appendChild(contentEl);
    conversationContainer.appendChild(messageEl);
    
    // 滚动到底部
    conversationContainer.scrollTop = conversationContainer.scrollHeight;
    
    return messageEl;
}

// 添加带有段落的AI消息
function addAIMessageWithSegments(segments) {
    // 移除思考中的消息
    const thinkingMessage = conversationContainer.querySelector('.ai-message.thinking');
    if (thinkingMessage) {
        conversationContainer.removeChild(thinkingMessage);
    }
    
    const messageEl = document.createElement('div');
    messageEl.className = 'message-bubble ai-message';
    
    for (const segment of segments) {
        if (segment.type === 'text') {
            const textEl = document.createElement('div');
            textEl.className = 'message-content';
            textEl.textContent = segment.content;
            messageEl.appendChild(textEl);
        } else if (segment.type === 'code') {
            const codeBlockEl = document.createElement('div');
            codeBlockEl.className = 'code-block';
            
            const preEl = document.createElement('pre');
            const codeEl = document.createElement('code');
            
            if (segment.language) {
                codeEl.className = `language-${segment.language}`;
            }
            
            codeEl.textContent = segment.content;
            
            preEl.appendChild(codeEl);
            codeBlockEl.appendChild(preEl);
            messageEl.appendChild(codeBlockEl);
            
            // 应用语法高亮
            hljs.highlightElement(codeEl);
        }
    }
    
    conversationContainer.appendChild(messageEl);
    
    // 滚动到底部
    conversationContainer.scrollTop = conversationContainer.scrollHeight;
    
    return messageEl;
}

// 更新文件树
function updateFileTree() {
    // 清空现有的文件列表
    filesList.innerHTML = '';

    // 创建一个对象来表示文件结构
    const fileStructure = {};

    // 遍历所有文件，构建文件结构
    Object.keys(files).forEach(filePath => {
        const parts = filePath.split('/');
        let current = fileStructure;
        
        parts.forEach((part, index) => {
            if (part === '') return;
            
            if (index === parts.length - 1) {
                // 这是文件
                current[part] = { type: 'file', path: filePath };
            } else {
                // 这是文件夹
                if (!current[part]) {
                    current[part] = { type: 'folder', children: {} };
                }
                current = current[part].children;
            }
        });
    });

    // 递归创建树节点
    function createTreeNode(structure, parentPath = '') {
        const container = document.createElement('div');
        container.classList.add('tree-container');

        // 按照文件夹在前，文件在后的顺序排序
        const sortedKeys = Object.keys(structure).sort((a, b) => {
            if (structure[a].type === structure[b].type) {
                return a.localeCompare(b);
            }
            return structure[a].type === 'folder' ? -1 : 1;
        });

        sortedKeys.forEach(name => {
            const item = structure[name];
            const itemPath = parentPath ? `${parentPath}/${name}` : name;
            const itemElement = document.createElement('div');
            
            if (item.type === 'folder') {
                itemElement.classList.add('folder-item');
                const folderHeader = document.createElement('div');
                folderHeader.classList.add('folder-header');
                folderHeader.innerHTML = `<span class="folder-icon">📁</span> ${name}`;
                
                const folderContent = document.createElement('div');
                folderContent.classList.add('folder-content');
                folderContent.style.display = 'none';
                
                // 递归处理子文件夹和文件
                folderContent.appendChild(createTreeNode(item.children, itemPath));
                
                // 添加展开/折叠功能
                folderHeader.addEventListener('click', () => {
                    const isHidden = folderContent.style.display === 'none';
                    folderContent.style.display = isHidden ? 'block' : 'none';
                    folderHeader.querySelector('.folder-icon').textContent = isHidden ? '📂' : '📁';
                });
                
                itemElement.appendChild(folderHeader);
                itemElement.appendChild(folderContent);
            } else {
                itemElement.classList.add('file-item');
                const fileIcon = getFileTypeIcon(name);
                itemElement.innerHTML = `<span class="file-icon">${fileIcon}</span> ${name}`;
                
                // 添加点击事件以显示文件内容
                itemElement.addEventListener('click', () => {
                    displayFileContent(item.path);
                    // 更新选中状态
                    document.querySelectorAll('.file-item').forEach(el => el.classList.remove('selected'));
                    itemElement.classList.add('selected');
                });
                
                // 如果这是当前正在编辑的文件，添加高亮
                if (item.path === currentEditingFile) {
                    itemElement.classList.add('selected');
                }
            }
            
            container.appendChild(itemElement);
        });

        return container;
    }

    // 获取文件类型图标
    function getFileTypeIcon(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const icons = {
            'py': '🐍',
            'js': '📜',
            'html': '🌐',
            'css': '🎨',
            'json': '📋',
            'md': '📝',
            'txt': '📄'
        };
        return icons[ext] || '📄';
    }

    // 创建并添加文件树
    const treeRoot = createTreeNode(fileStructure);
    filesList.appendChild(treeRoot);
}

// 根据文件名选择文件
function selectFileByName(fileName) {
    // 保存当前选中的文件
    currentFileTab = fileName;
    
    // 更新文件树选中状态
    updateFileTree();
    
    // 显示文件内容
    displayFileContent(fileName);
}

// 显示文件内容
function displayFileContent(filePath) {
    if (!files[filePath]) return;
    
    currentEditingFile = filePath;
    const content = files[filePath];
    
    // 获取文件扩展名
    const ext = filePath.split('.').pop().toLowerCase();
    
    // 确保代码容器存在
    let codeContainer = document.querySelector('.code-container');
    if (!codeContainer) {
        codeContainer = document.createElement('div');
        codeContainer.className = 'code-container';
        const editorContainer = document.querySelector('.code-editor-container');
        if (editorContainer) {
            editorContainer.appendChild(codeContainer);
        }
    }
    
    // 创建pre和code元素
    const pre = document.createElement('pre');
    const code = document.createElement('code');
    
    // 根据文件类型设置语言类
    code.className = `language-${ext}`;
    code.textContent = content;
    
    // 清空代码容器并添加新内容
    codeContainer.innerHTML = '';
    pre.appendChild(code);
    codeContainer.appendChild(pre);
    
    // 应用语法高亮
    hljs.highlightElement(code);
    
    // 移除打字效果
    if (typingInterval) {
        clearInterval(typingInterval);
        typingInterval = null;
    }
    
    // 滚动到顶部
    codeContainer.scrollTop = 0;
}

// 获取文件语言类
function getLanguageClass(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    
    const languageMap = {
        'js': 'javascript',
        'ts': 'typescript',
        'jsx': 'javascript',
        'tsx': 'typescript',
        'py': 'python',
        'html': 'html',
        'css': 'css',
        'scss': 'scss',
        'json': 'json',
        'md': 'markdown',
        'sql': 'sql',
        'sh': 'bash',
        'bash': 'bash',
        'txt': 'plaintext'
    };
    
    return languageMap[ext] || 'plaintext';
}

// 获取状态文本
function getStatusText(status) {
    switch (status) {
        case 'connected':
            return '已连接';
        case 'processing':
            return '生成中';
        case 'completed':
            return '已完成';
        case 'failed':
            return '失败';
        default:
            return status;
    }
}

// 显示首页
function showHomePage() {
    homePage.style.display = 'block';
    projectPage.style.display = 'none';
    
    // 重置表单
    promptForm.reset();
    submitBtn.disabled = false;
    submitBtn.textContent = '生成代码';
    temperatureValue.textContent = '0.1';
}

// 显示项目页面
function showProjectPage() {
    homePage.style.display = 'none';
    projectPage.style.display = 'flex';
    
    // 重置项目页面
    if (conversationContainer) {
        conversationContainer.innerHTML = '';
    }
    
    if (filesList) {
        filesList.innerHTML = '';
    }
    
    // 修复：使用querySelector获取代码容器元素
    const codeElement = document.querySelector('.code-container code');
    if (codeElement) {
        codeElement.textContent = '';
    }
    
    if (generatingIndicator) {
        generatingIndicator.style.display = 'flex';
    }
    
    // 重置文件相关变量
    files = {};
    fileHistory = {};
    currentEditingFile = null;
    currentFileTab = null;
    currentStep = null;
    currentMessage = null;
    
    // 重置状态
    updateStatus('pending');
} 
