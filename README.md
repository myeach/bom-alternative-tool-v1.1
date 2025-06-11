# 半岛智芯优选 - BOM元器件国产替代推荐工具

一个基于Streamlit和DeepSeek大语言模型的元器件替代方案推荐工具，帮助电子工程师快速找到国产替代元器件。

## 功能特点

- **单个元器件查询**：输入元器件型号，获取国产替代方案推荐
- **批量BOM替代**：上传BOM文件，批量获取所有元器件的替代方案
- **AI选型助手**：与AI对话，获取专业的元器件选型建议
- **历史记录**：保存查询历史，方便后续查看
- **数据导出**：支持Excel和CSV格式导出查询结果

## 安装指南

### 环境要求

- Python 3.8+
- Git (用于代码版本控制)

### 安装步骤

1. 克隆仓库到本地

```bash
git clone https://github.com/jingyuxu183/bom-alternative-tool-v1.0.git
cd bom-alternative-tool-v1.0
```

2. 安装依赖库

```bash
pip install -r requirements.txt
```

3. 配置环境变量

创建`.env`文件，添加以下内容：

```
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
NEXAR_CLIENT_ID=your_nexar_client_id
NEXAR_CLIENT_SECRET=your_nexar_client_secret
```

## 使用说明

### 启动应用

```bash
streamlit run frontend.py
```

或者指定端口运行：

```bash
streamlit run frontend.py --server.port 50485
```

### 功能使用

1. **单个元器件查询**：在"元器件替代查询"标签页输入元器件型号，点击"查询替代方案"
2. **AI选型助手**：在"AI选型助手"标签页与AI对话，询问元器件选型问题
3. **批量替代查询**：在"批量替代查询"标签页上传BOM文件，点击"开始批量查询"

## 代码修改与上传指南

如果您对代码进行了修改并希望将其上传到GitHub，请按照以下步骤操作：

### 1. 配置Git代理（如需使用VPN）

如果您需要通过VPN连接GitHub，请设置Git代理：

```bash
# 设置HTTP代理
git config --global http.proxy http://127.0.0.1:端口号

# 设置HTTPS代理
git config --global https.proxy https://127.0.0.1:端口号
```

例如，如果您的VPN端口是50223：

```bash
git config --global http.proxy http://127.0.0.1:50223
git config --global https.proxy https://127.0.0.1:50223
```

### 2. 查看修改状态

```bash
git status
```

### 3. 添加修改的文件

```bash
# 添加特定文件
git add frontend.py backend.py

# 或添加所有修改
git add .
```

### 4. 提交修改

```bash
git commit -m "描述您的修改内容"
```

### 5. 推送到GitHub

```bash
git push origin main
```

### 6. 常见问题解决

如果推送失败，可能是因为：

- **代理设置不正确**：确认VPN端口号正确
- **网络连接问题**：检查VPN是否正常工作
- **权限问题**：确认您有仓库的写入权限

可以尝试：

```bash
# 清除代理设置
git config --global --unset http.proxy
git config --global --unset https.proxy

# 重新设置代理
git config --global http.proxy http://127.0.0.1:正确端口号
git config --global https.proxy https://127.0.0.1:正确端口号
```

## 项目结构

- `frontend.py`: 前端界面实现
- `backend.py`: 后端逻辑和API调用
- `nexarClient.py`: Nexar API客户端
- `requirements.txt`: 项目依赖
- `custom_components/`: 自定义组件
- `.env`: 环境变量配置

## 依赖库

主要依赖库包括：

- streamlit: 用于构建Web界面
- openai: 用于调用DeepSeek API
- pandas: 用于数据处理
- python-dotenv: 用于环境变量管理
- xlrd/openpyxl: 用于Excel文件处理

详细依赖请参考`requirements.txt`文件。

## 贡献指南

欢迎提交Issues和Pull Requests来改进项目。在提交PR前，请确保：

1. 代码符合项目风格
2. 添加必要的注释和文档
3. 测试您的修改

## 许可证

本项目采用MIT许可证。详见LICENSE文件。 