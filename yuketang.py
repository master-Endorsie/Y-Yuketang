import asyncio
import logging
import self
import websockets
import json
import requests
import os
import asyncio
import re
import time
from websockets.exceptions import ConnectionClosed
from datetime import datetime as dt, timedelta, timezone as dt_timezone
import traceback
from util import *
from send import *
from random import *

current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

yt_config = config['yuketang']
timeout = yt_config['timeout']
domain = yt_config['domain']


class yuketang:
    shared_answers = {}

    # 发送课程状态消息
    def send_status_msg(self, lessonId, status):
        header = self.lessonIdDict[lessonId].get('header', '未知课程')
        self.msgmgr.sendMsg(f"{header}\n消息: {status}")
    def __init__(self, name, openId) -> None:
        self.name = name
        self.openId = openId
        self.cookie = ''
        self.lessonIdNewList = []
        self.lessonIdDict = {}

        # 新增配置项声明
        self.domain = yt_config.get('domain')
        self.timeout = yt_config.get('timeout')

        # 配置项安全获取（使用循环简化）
        config_keys = ['wx', 'dd', 'fs', 'an', 'ppt', 'si']
        for key in config_keys:
            setattr(self, key, yt_config.get(key))

        # 配置校验
        if not self.domain:
            raise ValueError("配置文件缺少domain参数")
        if not self.timeout:
            raise ValueError("配置文件缺少timeout参数")

        self.cookie_time = None
        self.lock = asyncio.Lock()
        self.config = self.load_config()
        self.cookie_valid_reminder_sent = False
        self.enable_ai = self.config.get('yuketang', {}).get('enable_ai', False)
        self.msgmgr = SendManager(
            openId=self.openId,
            wx=self.wx,
            dd=self.dd,
            fs=self.fs
        )

    # 获取当前文件的绝对路径，并构造配置文件的完整路径
    def load_config(self):

        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, 'config.json')

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError as e:
            raise Exception(f"配置文件 {config_path} 未找到") from e
        except json.JSONDecodeError as e:
            raise Exception(f"配置文件 {config_path} 格式错误：{str(e)}") from e

    # 自动获取和维护用户Cookie
    async def getcookie(self):
        def read_cookie():
            try:
                with open(f"{self.name}cookie", "r") as f:
                    lines = f.readlines()
                    self.cookie = lines[0].strip()
                    if len(lines) > 1:
                        # 直接存储datetime对象
                        self.cookie_time = dt.fromtimestamp(int(lines[1].strip()) / 1000, tz=tz)
            except Exception as e:
                self.msgmgr.sendMsg(f"读取cookie失败: {str(e)}")
                self.cookie = ''
                self.cookie_time = None

        read_cookie()

        # 检查 Cookie 是否过期
        if not self.cookie_time or (dt.now(tz) >= self.cookie_time):
            self.msgmgr.sendMsg("Cookie已失效，请重新扫码")
            await self.ws_controller(self.ws_login, retries=3, delay=10)
            read_cookie()

        # 验证有效性
        code = self.check_cookie()
        if code != 0:
            self.msgmgr.sendMsg("检测到Cookie无效，正在重新获取")
            await self.ws_controller(self.ws_login, retries=3, delay=10)
            read_cookie()

        # 新增提醒逻辑
        if code == 0 and self.cookie_time:
            remaining = (self.cookie_time - dt.now(tz)).total_seconds()
            if remaining > 0:
                if not self.cookie_valid_reminder_sent:  # 使用统一变量名
                    remaining_str = self.seconds_to_readable(remaining)
                    self.msgmgr.sendMsg(f"Cookie有效，剩余时间：{remaining_str}")
                    self.cookie_valid_reminder_sent = True  # 正确设置

                # 仅在未发送过提醒且剩余时间不足一天时触发
                if remaining < 86400 and not self.cookie_reminder_sent:
                    self.msgmgr.sendMsg("Cookie将在24小时内过期，请注意及时刷新")
                    self.cookie_reminder_sent = True  # 标记已发送

    # 输入与时间差计算 和 分解时间单位
    def seconds_to_readable(self, seconds):
        delta = timedelta(seconds=seconds)  # 使用导入的timedelta
        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        if seconds > 0 or not parts:
            parts.append(f"{seconds + 0.5:.0f}秒")  # 四舍五入
        return " ".join(parts)

    # 向服务器发送登录请求，携带用户凭证
    def weblogin(self, UserID, Auth):
        url = f"https://{self.domain}/pc/web_login"  # 假设 domain 是类属性
        data = {
            "UserID": UserID,
            "Auth": Auth
        }
        headers = {
            "referer": f"https://{self.domain}/web?next=/v2/web/index&type=3",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Content-Type": "application/json"
        }
        try:
            res = requests.post(url=url, headers=headers, json=data, timeout=self.timeout)  # 假设 timeout 是类属性
        except requests.exceptions.RequestException as e:
            print(f"登录失败: {e}")
            return

        # 正确拼接 Cookie
        cookies_list = []
        for k, v in res.cookies.items():
            cookies_list.append(f"{k}={v}")
        self.cookie = "; ".join(cookies_list)

        date = cookie_date(res)
        if date:
            self.cookie_time = convert_date(int(date))
            content = f"{self.cookie}\n{date}"
        else:
            content = self.cookie
            self.cookie_time = None  # 或其他默认值

        # 保存文件时确保路径安全
        filename = f"{self.name}_cookie.txt"  # 添加后缀并规范命名
        with open(filename, "w") as f:
            f.write(content)

    # 验证Cookie有效性
    def check_cookie(self):
        info = self.get_basicinfo()  # 1. 获取用户基本信息
        if not info:  # 2. 如果获取失败（如请求错误或无响应）
            return 2  # 返回状态码2：无法验证（可能因网络问题或Cookie已失效）
        if info.get("code") == 0:  # 3. 如果API返回code为0（通常表示成功）
            return 0  # 返回状态码0：Cookie有效
        return 1  # 返回状态码1：Cookie无效（但能收到非0的code响应）

    # 将HTTP响应中的认证令牌保存到课程对应的会话数据中
    def setAuthorization(self, res, lessonId):
        auth = res.headers.get("Set-Auth")
        if auth is not None:
            self.lessonIdDict[lessonId]['Authorization'] = f"Bearer {auth}"

    # 用于获取用户基本信息
    def get_basicinfo(self):
        url = f"https://{domain}/api/v3/user/basic-info"
        headers = {
            "Referer": f"https://{domain}/web?next=/v2/web/index&type=3",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "cookie": self.cookie
        }
        try:
            response = requests.get(url=url, headers=headers, timeout=timeout)
            response.raise_for_status()  # 检查HTTP状态码是否为2xx
            return response.json()
        except requests.exceptions.RequestException as e:
            return {}

    # 课程基本信息获取方法
    def lesson_info(self, lessonId):
        url = f"https://{domain}/api/v3/lesson/basic-info"
        headers = {
            "Referer": f"https://{domain}/lesson/fullscreen/v3/{lessonId}?source=5",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Cookie": self.cookie,
            "Authorization": self.lessonIdDict[lessonId]['Authorization']
        }
        try:
            res = requests.get(url=url, headers=headers, timeout=timeout)
            res.raise_for_status()  # 检查HTTP错误状态码
        except requests.exceptions.RequestException:
            return
        lesson_entry = self.lessonIdDict[lessonId]
        self.setAuthorization(res, lessonId)
        classroom_name = lesson_entry['classroomName']
        try:
            data = res.json().get('data', {})
            title = data.get('title', '未知标题')
            teacher_name = data.get('teacher', {}).get('name', '未知教师')
            start_time = convert_date(data.get('startTime', '')) if data.get('startTime') else '获取失败'
            lesson_entry['title'] = title
            lesson_entry['header'] = (
                f"课程: {classroom_name}\n"
                f"标题: {title}\n"
                f"教师: {teacher_name}\n"
                f"开始时间: {start_time}"
            )
        except Exception:
            lesson_entry['title'] = '未知标题'
            lesson_entry['header'] = (
                f"课程: {classroom_name}\n"
                f"标题: 获取失败\n"
                f"教师: 获取失败\n"
                f"开始时间: 获取失败"
            )

    # 获取当前进行中的课程列表
    def getlesson(self):
        url = f"https://{self.domain}/api/v3/classroom/on-lesson-upcoming-exam"  # 假设domain是类属性
        headers = {
            "referer": f"https://{self.domain}/web?next=/v2/web/index&type=3",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "cookie": self.cookie
        }
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)  # 假设timeout是类属性
            online_data = response.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            return False  # 请求或JSON解析失败

        try:
            classrooms = online_data['data']['onLessonClassrooms']
        except (KeyError, TypeError):
            classrooms = []

        self.lessonIdNewList = []
        active_lessons = set()

        # 处理新课程数据
        for item in classrooms:
            lessonId = item['lessonId']
            active_lessons.add(lessonId)
            if lessonId not in self.lessonIdDict:
                self.lessonIdNewList.append(lessonId)
                self.lessonIdDict[lessonId] = {
                    'start_time': time.time(),
                    'classroomName': item['courseName'],
                    'active': True
                }
            else:
                self.lessonIdDict[lessonId]['active'] = True

        # 清理过期课程
        to_delete = []
        for lessonId in self.lessonIdDict:
            if lessonId not in active_lessons:
                to_delete.append(lessonId)
            else:
                self.lessonIdDict[lessonId]['active'] = True  # 重置为True后会被后续覆盖

        # 执行清理
        for lessonId in to_delete:
            ws = self.lessonIdDict[lessonId].get('websocket', None)
            if ws:
                ws.close()
            del self.lessonIdDict[lessonId]

        return bool(self.lessonIdNewList)

    # 课程签到功能
    def lesson_checkin(self):
        headers_base = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Content-Type": "application/json; charset=utf-8",
            "cookie": self.cookie
        }
        for lessonId in self.lessonIdNewList:
            url = f"https://{self.domain}/api/v3/lesson/checkin"  # 假设domain为类属性
            headers = headers_base.copy()
            headers["referer"] = f"https://{self.domain}/lesson/fullscreen/v3/{lessonId}?source=5"
            
            data = {"source": 5, "lessonId": lessonId}
            try:
                res = requests.post(url, headers=headers, json=data, timeout=self.timeout)
                res.raise_for_status()  # 检查HTTP状态码
            except requests.exceptions.RequestException as e:
                self.msgmgr.sendMsg(f"请求失败: {str(e)}")
                continue
            
            self.setAuthorization(res, lessonId)
            self.lesson_info(lessonId)
            
            try:
                res_data = res.json().get('data', {})
                lesson_dict = self.lessonIdDict.get(lessonId, {})
                lesson_dict['Auth'] = res_data.get('lessonToken', '')
                lesson_dict['userid'] = res_data.get('identityId', '')
                self.lessonIdDict[lessonId] = lesson_dict  # 确保字典结构存在
            except (ValueError, KeyError, TypeError) as e:
                self.lessonIdDict[lessonId] = {'Auth': '', 'userid': ''}
                self.msgmgr.sendMsg(f"数据解析异常: {str(e)}")
            
            msg = res.json().get('msg', '')
            if msg == 'OK':
                self.send_status_msg(lessonId, "签到成功")
            elif msg == 'LESSON_END':
                self.send_status_msg(lessonId, "课程已结束")
            else:
                self.send_status_msg(lessonId, "签到失败")

    # 抓捕ppt图片
    def fetch_presentation(self, lessonId):
        lesson_info = self.lessonIdDict[lessonId]
        # 安全构建URL
        presentation_id = lesson_info.get('presentation')
        if not presentation_id:
            self.msgmgr.sendMsg(f"Error: presentation_id not found for lesson {lessonId}")
            return
        url = f"https://{domain}/api/v3/lesson/presentation/fetch"
        params = {"presentation_id": presentation_id}
        headers = {
            "referer": f"https://{domain}/lesson/fullscreen/v3/{lessonId}?source=5",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "cookie": self.cookie,
            "Authorization": lesson_info.get('Authorization', '')
        }
        try:
            res = requests.get(url, headers=headers, params=params, timeout=timeout)
            res.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.msgmgr.sendMsg(f"请求失败: {str(e)}")
            return
        try:
            info = res.json()
        except ValueError:
            self.msgmgr.sendMsg("无效的JSON响应")
            return
    
        slides = info.get('data', {}).get('slides', [])
        lesson_info['problems'] = {}
        covers = [slide['index'] for slide in slides if slide.get('cover') is not None]
        lesson_info['covers'] = covers
    
        for slide in slides:
            problem = slide.get("problem")
            if problem is None:
                continue
            slide_id = slide['id']
            problem_data = problem.copy()
            problem_data['index'] = slide['index']
            if problem_data['body'] == '':
                shapes = slide.get('shapes', [])
                if shapes:
                    min_left_item = min(shapes, key=lambda item: item.get('Left', 9999999))
                    problem_data['body'] = min_left_item.get('Text', '未知问题')
                else:
                    problem_data['body'] = '未知问题'
            lesson_info['problems'][slide_id] = problem_data
    
        if not lesson_info['problems']:
            self.msgmgr.sendMsg(f"{lesson_info['header']}\n问题列表: 无")
        else:
            self.msgmgr.sendMsg(
                f"{lesson_info['header']}\n{format_json_to_text(lesson_info['problems'], lesson_info.get('unlockedproblem', []))}")
    
        classroom_name = lesson_info.get('classroomName', '未知课程')
        safe_classroom = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5_\- ]', '_', classroom_name)
        base_dir = "ppt"
        folder_path = os.path.join(base_dir, safe_classroom)
        os.makedirs(folder_path, exist_ok=True)
        pdf_filename = f"{safe_classroom}-{lesson_info.get('title', '未知标题')}.pdf"
        output_pdf_path = os.path.join(folder_path, pdf_filename)
        asyncio.create_task(self.download_presentation(slides, folder_path, lessonId))
    
    async def download_presentation(self, slides, folder_path, lessonId):
        loop = asyncio.get_running_loop()
    
        # 检查 lessonId 是否存在
        if lessonId not in self.lessonIdDict:
            self.msgmgr.sendMsg(f"无效的课程序号: {lessonId}")
            return
    
        # 清空文件夹
        try:
            await loop.run_in_executor(None, clear_folder, folder_path)
        except Exception as e:
            self.msgmgr.sendMsg(f"清空文件夹失败: {str(e)}")
            return
    
        # 下载图片
        try:
            await loop.run_in_executor(None, download_images_to_folder, slides, folder_path)
        except Exception as e:
            self.msgmgr.sendMsg(f"下载图片失败: {str(e)}")
            return
    
        # 生成 PDF 文件名并清理非法字符
        classroom_name = re.sub(r'[\\/*?:"<>|]', '_', self.lessonIdDict[lessonId]['classroomName'])
        title = re.sub(r'[\\/*?:"<>|]', '_', self.lessonIdDict[lessonId]['title'])
        output_pdf_path = os.path.join(
            folder_path,
            f"{classroom_name}-{title}.pdf"
        )
    
        # 生成 PDF
        try:
            await loop.run_in_executor(None, images_to_pdf, folder_path, output_pdf_path)
        except Exception as e:
            self.msgmgr.sendMsg(f"生成 PDF 失败: {str(e)}")
            return
    
        # 最终检查文件是否存在
        if os.path.exists(output_pdf_path):
            self.msgmgr.sendFile(output_pdf_path)
        else:
            self.msgmgr.sendMsg(f"PPT 下载失败：未找到文件")

    async def answer(self, lessonId):
        # 缓存 lesson_info 到局部变量，减少重复字典访问
        lesson_info = self.lessonIdDict.get(lessonId)
        if not lesson_info:
            return

        try:
            problem_id = lesson_info['problemId']
            problem = lesson_info['problems'][problem_id]
        except KeyError as e:
            self.msgmgr.sendMsg(f"Missing key {e} in lessonIdDict for lesson {lessonId}")
            return

        # 安全性：确保 domain、cookie、Authorization 的存在性
        domain = self.domain  # 确保使用类属性 domain
        cookie = lesson_info.get('cookie', '')
        authorization = lesson_info.get('Authorization', '')

        url = f"https://{domain}/api/v3/lesson/problem/answer"
        headers = {
            "referer": f"https://{domain}/lesson/fullscreen/v3/{lessonId}?source=5",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "cookie": cookie,
            "Content-Type": "application/json",
            "Authorization": authorization
        }

        data = {
            "dt": int(time.time() * 1000),
            "problemId": problem_id,
            "problemType": problem.get('problemType'),
            "result": problem.get('answers', [])
        }

        try:
            # 使用具体异常捕获并记录错误
            res = requests.post(url=url, headers=headers, json=data, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            self.msgmgr.sendMsg(f"Request failed for lesson {lessonId}: {str(e)}")
            return

        self.setAuthorization(res, lessonId)
        # 使用 get() 避免 KeyError
        self.msgmgr.sendMsg(
            f"{lesson_info.get('header', 'No header')}\n"
            f"PPT: 第{problem.get('index', 'N/A')}页\n"
            f"问题: {problem.get('body', 'N/A')}\n"
            f"提交答案: {problem.get('answers', 'N/A')}"
        )

    # WebSocket连接重试限制
    async def ws_controller(self, func, *args, retries=3, delay=10):
        attempt = 0
        last_exception = None
        while attempt <= retries:
            try:
                await func(*args)
                return
            except (ConnectionError, TimeoutError) as e:  # 仅捕获预期异常
                last_exception = e
                attempt += 1
                if attempt <= retries:
                    await asyncio.sleep(delay)
                    logging.info(f"出现异常，尝试重试 ({attempt}/{retries})")
        # 所有重试失败后抛出异常
        if last_exception:
            raise last_exception
        else:
            raise RuntimeError("未捕获到异常但重试失败")

    # WebSocket请求二维码
    async def ws_login(self):
        uri = f"wss://{domain}/wsapp/"
        async with websockets.connect(uri, ping_timeout=180, ping_interval=5) as websocket:
            hello_message = {
                "op": "requestlogin",
                "role": "web",
                "version": 1.4,
                "type": "qrcode",
                "from": "web"
            }
            await websocket.send(json.dumps(hello_message))
            server_response = await recv_json(websocket)
            qrcode_url = server_response['ticket']
            download_qrcode(qrcode_url, self.name)
            self.msgmgr.sendImage(f"{self.name}qrcode.jpg")
            server_response = await asyncio.wait_for(recv_json(websocket), timeout=60)
            self.weblogin(server_response['UserID'], server_response['Auth'])

    # 标记问题是否提前结束
    async def countdown(self, limit):
        try:
            await asyncio.wait_for(self.stop_event.wait(), timeout=limit)
        except asyncio.TimeoutError:
            self.stop_event.set()
            try:
                self.msgmgr.sendMsg(f"问题正常结束")
            except:
                pass
        except asyncio.CancelledError:
            self.stop_event.set()
            try:
                self.msgmgr.sendMsg(f"问题已提前结束")
            except:
                pass
            raise
        else:
            try:
                self.msgmgr.sendMsg(f"问题已提前结束")
            except:
                pass

    async def listen_for_problemfinished(self, lessonId, limit):
        # 参数验证：确保limit为正数
        if limit <= 0:
            raise ValueError("limit must be a positive number")
        
        # 检查lessonId是否存在且包含有效的websocket
        lesson_info = self.lessonIdDict.get(lessonId)
        if not lesson_info or 'websocket' not in lesson_info:
            self.msgmgr.sendMsg(f"Lesson ID {lessonId} not found or missing websocket")
            self.stop_event.set()
            return
        
        websocket = lesson_info['websocket']
        
        while not self.stop_event.is_set():
            try:
                server_response = await asyncio.wait_for(recv_json(websocket), timeout=limit)
                # 检查'op'键是否存在
                if 'op' in server_response and server_response['op'] == "problemfinished":
                    self.stop_event.set()
                    break
            except asyncio.TimeoutError:
                self.stop_event.set()
                break
            except (ConnectionError, ConnectionClosed) as e:
                self.msgmgr.sendMsg(f"{lesson_info['header'] if lesson_info else ''}\n消息: 连接断开 - {str(e)}")
                self.stop_event.set()
                break

    async def receive_messages(self, lessonId):
        await self.pull_probleminfo(lessonId)
        while not self.stop_event.is_set():
            try:
                # 提取键值检查并捕获KeyError
                lesson_info = self.lessonIdDict.get(lessonId)
                if not lesson_info:
                    raise KeyError(f"无法找到对应的WebSocket连接: {lessonId}")
                websocket = lesson_info['websocket']
                
                server_response = await recv_json(websocket)
            except (KeyError, ConnectionError, json.JSONDecodeError) as e:
                self.msgmgr.sendMsg(f"{lesson_info['header'] if lesson_info else ''}\n消息: 连接断开或响应解析失败")
                break
            except Exception as e:
                # 捕获其他异常但保留原意
                self.msgmgr.sendMsg(f"未知错误: {str(e)}")
                break
                
            op = server_response.get('op')
            if op == "probleminfo":
                limit = server_response.get('limit')
                # 验证limit类型和有效性
                if isinstance(limit, int) and limit > 0:
                    self.msgmgr.sendMsg(f"问题开始，倒计时 {limit} 秒")
                    # 处理子任务异常并等待完成
                    try:
                        await asyncio.gather(
                            self.countdown(limit),
                            self.listen_for_problemfinished(lessonId, limit),
                            return_exceptions=True  # 捕获子任务异常
                        )
                    except Exception as e:
                        self.msgmgr.sendMsg(f"任务执行失败: {str(e)}")
                    finally:
                        break  # 无论是否异常均退出循环
                else:
                    self.msgmgr.sendMsg(f"问题无倒计时或limit无效")
            elif op == "problemfinished":
                self.stop_event.set()
                self.msgmgr.sendMsg(f"问题已结束")
                break

    async def fetch_answers(self, lessonId):
        while not self.stop_event.is_set():
            try:
                # 获取幻灯片信息，处理可能的异常
                self.fetch_problems(lessonId)
            except Exception as e:
                print(f"Error fetching problems: {e}")
                await asyncio.sleep(2)
                continue  # 继续循环
            
            # 缓存lesson_dict，避免重复访问字典
            lesson_dict = self.lessonIdDict.get(lessonId)
            if not lesson_dict:
                await asyncio.sleep(2)
                continue
            
            # 获取当前问题ID并校验有效性
            current_problem_id = lesson_dict.get('problemId')
            if current_problem_id is None:
                await asyncio.sleep(2)
                continue
            
            # 获取问题列表并校验索引范围
            problems = lesson_dict.get('problems', [])
            if current_problem_id < 0 or current_problem_id >= len(problems):
                await asyncio.sleep(2)
                continue
            
            current_problem = problems[current_problem_id]
            answers = current_problem.get('answers')
            
            if answers:
                try:
                    await self.answer(lessonId)
                except Exception as e:
                    print(f"Error submitting answer: {e}")
                finally:
                    self.stop_event.set()
                    break  # 提交答案后退出循环
            
            await asyncio.sleep(2)

    async def pull_probleminfo(self, lessonId):
        try:
            lesson_dict = self.lessonIdDict[lessonId]
        except KeyError:
            raise KeyError(f"Lesson ID {lessonId} not found")
        
        # 构造消息
        probleminfo_message = {
            "op": "probleminfo",
            "lessonid": lessonId,
            "problemid": lesson_dict['problemId'],
            "msgid": lesson_dict['msgid']
        }
    
        # 发送消息并捕获异常
        try:
            await lesson_dict['websocket'].send(json.dumps(probleminfo_message))
        except websockets.exceptions.ConnectionClosed as e:
            # 根据需求处理异常（如记录日志或重连）
            logging.error(f"WebSocket closed for lesson {lessonId}: {e}")
    
        # 使用锁保护msgid自增操作
        async with self.lock:
            current_msgid = lesson_dict['msgid']
            lesson_dict['msgid'] = current_msgid + 1
    # 核心方法
    async def ws_lesson(self, lessonId):
        flag_ppt = 1
        flag_si = 1
        self.lessonIdDict[lessonId]['msgid'] = 1

        def del_dict():
            nonlocal flag_ppt, flag_si
            flag_ppt = 1
            flag_si = 1
            keys_to_remove = ['presentation', 'si', 'unlockedproblem', 'covers']
            for key in keys_to_remove:
                if self.lessonIdDict[lessonId].get(key) is not None:
                    del self.lessonIdDict[lessonId][key]

        del_dict()
        uri = f"wss://{domain}/wsapp/"
        async with websockets.connect(uri, ping_timeout=180, ping_interval=15) as websocket:
            # 发送 "hello" 消息以建立连接
            hello_message = {
                "op": "hello",
                "userid": self.lessonIdDict[lessonId]['userid'],
                "role": "student",
                "auth": self.lessonIdDict[lessonId]['Auth'],
                "lessonid": lessonId
            }
            await websocket.send(json.dumps(hello_message))
            self.lessonIdDict[lessonId]['websocket'] = websocket
            while True and time.time() - self.lessonIdDict[lessonId]['start_time'] < 36000:
                try:
                    server_response = await recv_json(websocket)
                except Exception as e:
                    self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 连接断开")
                    break
                op = server_response['op']
                if op == "hello" or op == "fetchtimeline":
                    reversed_timeline = list(reversed(server_response['timeline']))
                    for item in reversed_timeline:
                        if 'pres' in item:
                            if flag_ppt == 0 and self.lessonIdDict[lessonId]['presentation'] != item['pres']:
                                del_dict()
                                self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 课件更新")
                            self.lessonIdDict[lessonId]['presentation'] = item['pres']
                            self.lessonIdDict[lessonId]['si'] = item['si']
                            break
                    if server_response.get('presentation'):
                        if flag_ppt == 0 and self.lessonIdDict[lessonId]['presentation'] != server_response[
                            'presentation']:
                            del_dict()
                            self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 课件更新")
                        self.lessonIdDict[lessonId]['presentation'] = server_response['presentation']
                    if server_response.get('slideindex'):
                        self.lessonIdDict[lessonId]['si'] = server_response['slideindex']
                    if server_response.get('unlockedproblem'):
                        self.lessonIdDict[lessonId]['unlockedproblem'] = server_response['unlockedproblem']
                elif op == "showpresentation" or op == "presentationupdated" or op == "presentationcreated":
                    if server_response.get('presentation'):
                        if flag_ppt == 0 and self.lessonIdDict[lessonId]['presentation'] != server_response[
                            'presentation']:
                            del_dict()
                            self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 课件更新")
                        self.lessonIdDict[lessonId]['presentation'] = server_response['presentation']
                    if server_response.get('slideindex'):
                        self.lessonIdDict[lessonId]['si'] = server_response['slideindex']
                    if server_response.get('unlockedproblem'):
                        self.lessonIdDict[lessonId]['unlockedproblem'] = server_response['unlockedproblem']
                elif op == "slidenav":
                    if server_response['slide'].get('pres'):
                        if flag_ppt == 0 and self.lessonIdDict[lessonId]['presentation'] != server_response['slide'][
                            'pres']:
                            del_dict()
                            self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 课件更新")
                        self.lessonIdDict[lessonId]['presentation'] = server_response['slide']['pres']
                    if server_response['slide'].get('si'):
                        self.lessonIdDict[lessonId]['si'] = server_response['slide']['si']
                    if server_response.get('unlockedproblem'):
                        self.lessonIdDict[lessonId]['unlockedproblem'] = server_response['unlockedproblem']
                elif op == "unlockproblem":
                    if server_response['problem'].get('pres'):
                        if flag_ppt == 0 and self.lessonIdDict[lessonId]['presentation'] != server_response['problem'][
                            'pres']:
                            del_dict()
                            self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 课件更新")
                        self.lessonIdDict[lessonId]['presentation'] = server_response['problem']['pres']
                    if server_response['problem'].get('si'):
                        self.lessonIdDict[lessonId]['si'] = server_response['problem']['si']
                    if server_response.get('unlockedproblem'):
                        self.lessonIdDict[lessonId]['unlockedproblem'] = server_response['unlockedproblem']
                    self.lessonIdDict[lessonId]['problemId'] = server_response['problem']['prob']
                    text_result = f"PPT: 第{self.lessonIdDict[lessonId]['problems'][self.lessonIdDict[lessonId]['problemId']]['index']}页\n问题: {self.lessonIdDict[lessonId]['problems'][self.lessonIdDict[lessonId]['problemId']].get('body', '未知问题')}\n"
                    answers = self.lessonIdDict[lessonId]['problems'][self.lessonIdDict[lessonId]['problemId']].get(
                        'answers', [])
                    if 'options' in self.lessonIdDict[lessonId]['problems'][self.lessonIdDict[lessonId]['problemId']]:
                        for option in self.lessonIdDict[lessonId]['problems'][self.lessonIdDict[lessonId]['problemId']][
                            'options']:
                            text_result += f"- {option['key']}: {option['value']}\n"
                    if answers not in [[], None, 'null']:
                        answer_text = ', '.join(answers)
                        text_result += f"答案: {answer_text}\n"
                    else:
                        text_result += "答案: 暂无\n"
                    self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n解锁问题:\n{text_result}")
                    if self.an:
                        self.stop_event = asyncio.Event()
                        if flag_ppt == 1 and self.lessonIdDict[lessonId].get('presentation') is not None:
                            flag_ppt = 0
                            self.fetch_presentation(lessonId)

                        try:
                            await asyncio.wait_for(
                                asyncio.gather(
                                    self.receive_messages(lessonId),
                                    self.fetch_answers(lessonId)
                                ),
                                timeout=420  # 设置超时时间为 7 分钟
                            )
                        except asyncio.TimeoutError:
                            # 处理超时的情况，例如记录日志或者通知用户
                            self.msgmgr.sendMsg(f"问题超时已取消")
                        self.stop_event.clear()

                elif op == "lessonfinished":
                    self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 下课了")
                    break
                if flag_ppt == 1 and self.lessonIdDict[lessonId].get('presentation') is not None:
                    flag_ppt = 0
                    self.fetch_presentation(lessonId)
                if flag_si == 1 and self.lessonIdDict[lessonId].get('si') is not None and self.lessonIdDict[
                    lessonId].get('covers') is not None and self.lessonIdDict[lessonId]['si'] in \
                        self.lessonIdDict[lessonId]['covers']:
                    self.msgmgr.sendMsg(
                        f"{self.lessonIdDict[lessonId]['header']}\n消息: 正在播放PPT第{self.lessonIdDict[lessonId]['si']}页")
                    if self.si:
                        del self.lessonIdDict[lessonId]['si']
                    else:
                        flag_si = 0
            self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 连接关闭")
            del self.lessonIdDict[lessonId]
            yuketang.shared_answers = {}

    async def lesson_attend(self):
        tasks = [asyncio.create_task(self.ws_lesson(lessonId)) for lessonId in self.lessonIdNewList]
        asyncio.gather(*tasks)
        self.lessonIdNewList = []

    # 获取课程问题 & 题型判断
    def fetch_problems(self, lessonId):
        url = f"https://{domain}/api/v3/lesson/presentation/fetch?presentation_id={self.lessonIdDict[lessonId]['presentation']}"
        headers = {
            "referer": f"https://{domain}/lesson/fullscreen/v3/{lessonId}?source=5",
            "User-Agent": "Mozilla/5.0 ...",
            "cookie": self.cookie,
            "Authorization": self.lessonIdDict[lessonId]['Authorization']
        }
        res = requests.get(url, headers=headers, timeout=timeout)
        self.setAuthorization(res, lessonId)
        info = res.json()
        slides = info['data']['slides']

        for slide in slides:
            if slide['id'] == self.lessonIdDict[lessonId]['problemId']:
                if slide.get("problem") is not None:
                    problem = slide['problem']
                    problem['index'] = slide['index']

                    # 处理问题正文缺失
                    if problem['body'] == '':
                        shapes = slide.get('shapes', [])
                        if shapes:
                            min_left_item = min(shapes, key=lambda item: item.get('Left', 9999999))
                            problem['body'] = min_left_item.get('Text', '未知问题')
                        else:
                            problem['body'] = '未知问题'

                    # 根据题型和开关决定是否调用AI
                    question_type = problem.get('problemType', 0)
                    if not self.enable_ai:  # 如果开关关闭
                        problem['answers'] = []
                        self.msgmgr.sendMsg("AI答题功能已关闭，跳过答题")
                        break
                    else:
                        if question_type == 4:  # 填空题：不使用AI
                            problem['answers'] = []
                            self.msgmgr.sendMsg("填空题：暂时不支持AI答题")
                            break
                        elif question_type == 5:  # 单选题：调用AI
                            ai_answer = self.get_answer_from_ai(problem, lessonId, is_multiple=False)
                            if ai_answer:
                                problem['answers'] = [ai_answer]
                                self.msgmgr.sendMsg(f"单选题答案：{ai_answer} 已提交")
                                break
                        elif question_type == 6:  # 多选题：调用AI
                            ai_answer = self.get_answer_from_ai(problem, lessonId, is_multiple=True)
                            if ai_answer:
                                problem['answers'] = ai_answer
                                self.msgmgr.sendMsg(f"多选题答案：{','.join(ai_answer)} 已提交")
                                break
                        else:  # 其他题型：默认调用AI
                            ai_answer = self.get_answer_from_ai(problem, lessonId)
                            if ai_answer:
                                problem['answers'] = [ai_answer]
                                self.msgmgr.sendMsg(f"通用题型答案：{ai_answer} 已提交")
                                break

    # AI自动答题
    def get_answer_from_ai(self, problem, lessonId, is_multiple=False):
        if not self.enable_ai:  # 如果开关关闭，直接返回空答案
            return None

        question = problem.get('body', '未知问题')
        options = problem.get('options', [])
        question_type = problem.get('problemType', 0)

        # 构造提示词
        if question_type == 5:  # 单选题
            prompt = f"题目：{question}\n选项：{options}\n请选择正确答案（仅回复选项字母，如A/B/C/D）："
        elif question_type == 6:  # 多选题
            prompt = f"题目：{question}\n选项：{options}\n请选择所有正确答案（用逗号分隔选项字母，如A,B,C）："
        else:
            prompt = f"问题类型：{question_type}\n题目：{question}\n请给出答案："

        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self.config['yuketang']['dashscope_api_key'],
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )

            completion = client.chat.completions.create(
                model="qwq-plus-latest",
                messages=[{"role": "user", "content": prompt}],
                stream=True
            )

            answer = ""
            for chunk in completion:
                if hasattr(chunk.choices[0].delta, 'content'):
                    answer += chunk.choices[0].delta.content

            # 清洗答案
            if question_type == 5:  # 单选题
                answer = answer.strip().upper()[:1]
                if answer in ["A", "B", "C", "D"]:
                    return answer
                else:
                    return None
            elif question_type == 6:  # 多选题
                answers = answer.strip().upper().split(",")
                valid_answers = []
                for a in answers:
                    a = a.strip()
                    if a in ["A", "B", "C", "D", "E", "F"]:
                        valid_answers.append(a)
                return valid_answers if valid_answers else None
            else:
                return answer.strip()
        except Exception as e:
            self.msgmgr.sendMsg(f"AI调用失败: {str(e)}")
            return None


async def ykt_user(ykt):
    await ykt.getcookie()
    while True:
        if ykt.getlesson():
            ykt.lesson_checkin()
            await ykt.lesson_attend()
        await asyncio.sleep(30)
