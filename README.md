# Y-Yuketang 长江雨课堂自动化工具

## 🚀 项目简介
本项目支持自动签到、AI自动答题（画饼）、PPT下载。基于 Python 异步框架实现多线程监听，适配企业微信推送。

---

## 📦 安装依赖
#### Windows 系统
```bash
pip install -r requirements.txt
```
请确保已安装 [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)。

Linux 系统依赖需要额外安装 pyzbar 依赖 `sudo apt-get install libzbar0 libzbar-dev`


---

## 📖 快速开始
### 步骤 1：配置 `config.json`

### 步骤 2：运行程序
```bash
python main.py
```
### 步骤 3：选择雨课堂服务器
### 步骤 4：扫码登录

---

## 📄 配置文件说明
### 配置文件结构 (`config.json`)
```json
{
    "yuketang": {
        "domain": "",                                           
        "first_run": true,                                      
        "wx": false,                                            # 是否启用企业微信推送
        "an": false,                                                        
        "si": false,                                            # 是否实时推送PPT当前页码
        "enable_ai": false,                                     
        "timeout": 30,                                          
        "dashscope_api_key": "ds-XXXXXXXXXXXXXXXXXXXXXXXX"      
    },
```

---

## 📌 功能特性
### 1. 自动签到
- **触发频率**：每 30 秒自动检查。

### 2. AI自动答题（画饼
- **题型支持**：单选、多选。

### 3. PPT 下载
- **存储路径**：`./{lessonId}/`（如 `./2023秋-机器学习-0/`）。
- **文件格式**：PPT图片转为 PDF 文件，命名格式 `课程名-标题.pdf`。

---

## 🛠️ 推送配置指南
### 企业微信 (`wx`)
1. 注册企业微信应用，获取 `agentId`、`secret`、`companyId`，并在应用管理中添加企业可信ip
2. 在 `config.json` 中启用 `yuketang.wx = true`，并在下面填写所需配置：
   ```json
   "send": {
     "wx": {
       "touser": "@all",
       "agentId": "你的AgentID",
       "secret": "你的Secret",
       "companyId": "企业ID"
     }
   }
   ```

### 📊 推送平台限制
| 推送方式 | 消息限制 | 文件限制  |
|-------|---------|---------|
| 企业微信  | 500 字符 | 20MB (20971520) |

---

## ⚠️ 免责声明
### 1. 本项目保证永久开源，没有任何收费，请勿二次贩卖。
### 2. 若本项目被用于非法用途，开发团队将会停止更新或删除项目。
### 3. 联系我们
- **GitHub Issues**：[提交问题或建议](https://github.com/master-Endorsie/Y-Yuketang/issues)
> **注意**：本项目仍处于开发阶段，完全无法使用，建议优先使用下列原项目代码。
### 🌟 特别鸣谢 🌟

| 项目名称                | GitHub仓库                                                                 |
|-------------------------|---------------------------------------------------------------------------|
| **lazytool**            | [timeflykai/lazytool](https://github.com/timeflykai/lazytool/tree/main)    |
| **thuhollow2/Hetangyuketang** | [thuhollow2/Hetangyuketang](https://github.com/thuhollow2/Hetangyuketang) |
| **yuketang**            | [Mathew-Carl/yuketang](https://github.com/Mathew-Carl/yuketang)            |


---

## 📌 技术架构
### 1.异步事件驱动框架
技术栈：基于 Python 的 asyncio 和 websockets 库实现异步事件驱动。  
功能：  
支持多用户并发处理（通过 UserManager 管理用户任务）。  
实时监听课程状态变化（如签到、PPT更新、答题事件）。  
通过 WebSocket 与雨课堂服务器保持长连接。  
### 2. 模块化设计  
关键模块：  
main.py：程序入口，启动异步事件循环。  
user_manager.py：管理用户实例，为每个用户启动独立的异步任务。  
yuketang.py：核心业务逻辑模块，处理：用户登录、Cookie 管理、课程签到、PPT 下载和答题逻辑。  
WebSocket 监听课程事件。  
send.py：消息推送模块，支持企业微信平台  
util.py：工具函数，包括文件操作、时间处理、二维码生成等。  

---

## 📝 附录
### 推送示例
```plaintext
课程: 自动控制原理★
标题: 第2章
教师: 小美
开始时间: 00日 星期天 00时00分00秒
消息: 签到成功
```