# Y-Yuketang 雨课堂自动化工具

## 🚀 项目简介
本项目支持自动签到、AI自动答题（画饼）、PPT下载及课堂进度监控。基于 Python 异步框架实现多线程监听，适配企业微信推送。

---

## 📦 安装与依赖
### 依赖安装
```bash
pip install -r requirements.txt
```

#### Linux 系统依赖
```bash
sudo apt-get install libzbar0 libzbar-dev  # 安装 pyzbar 依赖
```

#### Windows 系统
确保已安装 [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)。

---

## 🎚️ 运行方式
```bash
python main.py
```

---

## 📄 配置文件说明
### 配置文件结构 (`config.json`)
```json
{
  "yuketang": {
    "domain": "changjiang.yuketang.cn",          // 雨课堂域名（默认）
    "classroomCodeList": ["JZOJ5C", "G84UAB"],  // 班级邀请码/课堂暗号列表
    "classroomWhiteList": [],             // 白名单课程（完全匹配）
    "clashroomBlackList": ["课程名1"],    // 黑名单课程
    "clashroomStartTimeDict": {
      "课程名": {"1": "08:30", "3": "14:00"}  // 课程签到时间限制（周1-7对应周一到周日）
    },
    "an": false,          // 自动答题开关
    "ppt": false,         // 自动下载PPT开关
    "si": false,          // PPT进度推送开关
    "timeout": 30        // API超时时间（秒）
  },
  "users": [
    {"name": "user1", "openId": "OPENID1"},
    {"name": "user2", "openId": "OPENID2"}
  ]
}
```

### 配置项详细说明
#### **`Y-Yuketang` 配置**
| 参数名                  | 类型    | 说明                                                                 |
|-------------------------|---------|--------------------------------------------------------------------|
| `domain`                | String  | 长江雨课堂域名 `changjiang.yuketang.cn` |
| `classroomCodeList`     | Array   | 需要加入的班级邀请码/课堂暗号列表                                           |
| `clashroomStartTimeDict`| Object  | 课程签到时间限制（示例：`"课程名": {"1": "08:30"}`）                       |
| `an`                    | Boolean | 启用自动答题（需多人共享答案库）                                        |
| `ppt`                   | Boolean | 自动下载PPT并生成PDF                                                    |
| `si`                    | Boolean | 实时推送PPT当前页码（需谨慎使用，避免消息轰炸）                          |

#### **`users` 配置**
每个用户需包含：
```json
{
  "name": "用户标识（如学号）",
  "openId": "雨课堂OpenID（扫码登录后自动生成）"
}
```

---

## 📌 功能特性
### 1. 自动签到
- **触发频率**：每 30 秒检查新课程。
- **支持场景**：通过邀请码加入课程并自动签到。

### 2. 自动答题
- **题型支持**：单选、多选、填空（依赖共享答案库）。
- **限制**：需多人同时运行以共享答案。

### 3. PPT 下载与监控
- **存储路径**：`./{lessonId}/`（如 `./2023秋-机器学习-0/`）。
- **文件格式**：PPT图片转为 PDF 文件，命名格式 `课程名-标题.pdf`。

---

## 🛠️ 推送配置指南
### 企业微信 (`wx`)
1. 注册企业微信应用，获取 `agentId`、`secret`、`companyId`。
2. 在 `config.json` 中启用 `yuketang.wx = true`，并填写 `send.wx` 配置：
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

---

## 📊 关键配置参数
| 推送方式 | 消息限制 (`msgLimit`) | 文件限制 (`dataLimit`) |
|----------|----------------------|----------------------|
| 企业微信 (`wx`) | 500 字符              | 20MB (20971520)       |

---

## 🚨 常见问题与排查
### 1. **自动答题失败**
- **可能原因**：
  - `an` 未设为 `true`。
  - 共享答案库 (`shared_answers`) 为空。
- **解决方案**：
  - 确保 `an: true` 并多人同时运行程序并有人提交答案

### 2. **PPT 下载失败**
- **排查步骤**：
  1. 检查 `util.threads` 线程数是否过低。
  2. 确认 `util.timeout` 是否足够（默认 30 秒）。

---

## ⚠️ 项目声明
1. **当前状态**：
   - **已实现**：自动签到、PPT 下载、基础答题逻辑。
   - **待开发**：AI 自动答题（框架搭建中）、稳定性优化。

2. **免责声明**：
   - 本项目为学习作品，可能存在兼容性问题。
   - 建议优先尝试原项目：[yuketang](https://github.com/Mathew-Carl/yuketang),[thuhollow2/Hetangyuketang](https://github.com/thuhollow2/Hetangyuketang)。

---

## 📖 快速开始
### 步骤 1：配置 `config.json`

### 步骤 2：运行程序
```bash
python main.py
```

### 步骤 3：扫码登录
1. 程序生成 `userXqrcode.jpg`，扫码后获取 Cookie。
2. 控制台输出示例：
   ```
   MSG: Cookie有效，剩余时间：1天 2小时。
   ```

---

## 📌 技术架构
```mermaid
graph TD
    A[main.py] --> B[yuketang类]
    B --> C[Cookie管理(getcookie)]
    B --> D[WebSocket监听(ws_lesson)]
    B --> E[自动答题(fetch_answers)]
    F[UserManager] --> A
```

---

## 📢 声明与联系方式
### 项目状态
> **注意**：本项目仍处于开发阶段，可能存在未修复的 Bug。建议优先使用原项目代码。

### 联系我们
- **GitHub Issues**：[提交问题或建议](https://github.com/your-repo/Y-Yuketang/issues)
- **作者邮箱**：your-email@example.com

---

## 📝 附录
### 1. 依赖库列表
```python
requests        # HTTP请求
websockets      # WebSocket通信
aiofiles        # 异步文件操作
pyzbar          # 二维码识别
Pillow          # 图像处理
python-dateutil # 时间转换
openai          # OpenAI API
```

### 2. 推送示例
```plaintext
课程: 大学外语
标题: 大学英语 四级考试（2）
教师: 小美
开始时间: 2025年03月11日09时41分55秒
消息: 签到成功
```

---

## 🛠️ 贡献与反馈
- **提交 Issues**：描述 Bug 或功能建议。
- **修复代码**：优先处理 `TODO` 注释中的未完成部分（如 AI 答题模块）。
