import asyncio
import websockets
import json
import requests
import os
import time
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

    def __init__(self, name, openId) -> None:
        self.name = name
        self.openId = openId
        self.cookie = ''
        self.cookie_time = ''

        self.lessonIdNewList = []
        self.lessonIdDict = {}
        self.wx = yt_config['wx']
        self.dd = yt_config['dd']
        self.fs = yt_config['fs']
        self.an = yt_config['an']
        self.ppt = yt_config['ppt']
        self.si = yt_config['si']
        self.cookie_time = None
        self.config = self.load_config()
        self.cookie_valid_reminder_sent = False
        self.enable_ai = self.config['yuketang'].get('enable_ai', False)
        self.msgmgr = SendManager(openId=self.openId, wx=self.wx, dd=self.dd, fs=self.fs)

    def load_config(self):
        current_dir = os.path.dirname(__file__)
        os.chdir(current_dir)
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)

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
        url = f"https://{domain}/pc/web_login"
        data = {
            "UserID": UserID,
            "Auth": Auth
        }
        headers = {
            "referer": f"https://{domain}/web?next=/v2/web/index&type=3",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Content-Type": "application/json"
        }
        try:
            res = requests.post(url=url, headers=headers, json=data, timeout=timeout)
        except Exception as e:
            print(f"登录失败: {e}")
            return
        cookies = res.cookies
        self.cookie = ""
        for k, v in cookies.items():
            self.cookie += f'{k}={v};'
        date = cookie_date(res)
        if date:
            content = f'{self.cookie}\n{date}'
            self.cookie_time = convert_date(int(date))
        else:
            content = self.cookie
        with open(f"{self.name}cookie", "w") as f:
            f.write(content)
        self.cookie_time = convert_date(int(date))

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
        if res.headers.get("Set-Auth") is not None:
            self.lessonIdDict[lessonId]['Authorization'] = "Bearer " + res.headers.get("Set-Auth")

    # 用于获取用户基本信息
    def get_basicinfo(self):
        url = f"https://{domain}/api/v3/user/basic-info"
        headers = {
            "referer": f"https://{domain}/web?next=/v2/web/index&type=3",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "cookie": self.cookie
        }
        try:
            res = requests.get(url=url, headers=headers, timeout=timeout).json()
            return res
        except Exception as e:
            return {}

    # 课程基本信息获取方法
    def lesson_info(self, lessonId):
        url = f"https://{domain}/api/v3/lesson/basic-info"
        headers = {
            "referer": f"https://{domain}/lesson/fullscreen/v3/{lessonId}?source=5",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "cookie": self.cookie,
            "Authorization": self.lessonIdDict[lessonId]['Authorization']
        }
        try:
            res = requests.get(url=url, headers=headers, timeout=timeout)
        except Exception as e:
            return
        self.setAuthorization(res, lessonId)
        classroomName = self.lessonIdDict[lessonId]['classroomName']
        try:
            self.lessonIdDict[lessonId]['title'] = res.json()['data']['title']
            self.lessonIdDict[lessonId][
                'header'] = f"课程: {classroomName}\n标题: {self.lessonIdDict[lessonId]['title']}\n教师: {res.json()['data']['teacher']['name']}\n开始时间: {convert_date(res.json()['data']['startTime'])}"
        except Exception as e:
            self.lessonIdDict[lessonId]['title'] = '未知标题'
            self.lessonIdDict[lessonId][
                'header'] = f"课程: {classroomName}\n标题: 获取失败\n教师: 获取失败\n开始时间: 获取失败"

    # 获取当前进行中的课程列表
    def getlesson(self):
        url = f"https://{domain}/api/v3/classroom/on-lesson-upcoming-exam"
        headers = {
            "referer": f"https://{domain}/web?next=/v2/web/index&type=3",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "cookie": self.cookie
        }
        try:
            online_data = requests.get(url=url, headers=headers, timeout=timeout).json()
        except Exception as e:
            return False
        try:
            self.lessonIdNewList = []
            if online_data['data']['onLessonClassrooms'] == []:
                for lessonId in self.lessonIdDict:
                    self.lessonIdDict[lessonId].get('websocket', '').close()
                self.lessonIdDict = {}
                return False
            for item in online_data['data']['onLessonClassrooms']:
                # 移除所有过滤条件
                lessonId = item['lessonId']
                if lessonId not in self.lessonIdDict:
                    self.lessonIdNewList.append(lessonId)
                    self.lessonIdDict[lessonId] = {}
                    self.lessonIdDict[lessonId]['start_time'] = time.time()
                    self.lessonIdDict[lessonId]['classroomName'] = item['courseName']
                self.lessonIdDict[lessonId]['active'] = '1'
            to_delete = [lessonId for lessonId, details in self.lessonIdDict.items() if
                         not details.get('active', '0') == '1']
            for lessonId in to_delete:
                del self.lessonIdDict[lessonId]
                self.lessonIdDict[lessonId].get('websocket', '').close()
            for lessonId in self.lessonIdDict:
                self.lessonIdDict[lessonId]['active'] = '0'
            if self.lessonIdNewList:
                return True
            else:
                return False
        except Exception as e:
            return False

    # 课程签到功能
    def lesson_checkin(self):
        for lessonId in self.lessonIdNewList:
            # 1. 发送签到请求
            url = f"https://{domain}/api/v3/lesson/checkin"
            headers = {
                "referer": f"https://{domain}/lesson/fullscreen/v3/{lessonId}?source=5",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
                "Content-Type": "application/json; charset=utf-8",
                "cookie": self.cookie
            }
            data = {
                "source": 5,
                "lessonId": lessonId
            }
            try:
                res = requests.post(url, headers=headers, json=data, timeout=timeout)
            except Exception as e:
                return  # 网络请求失败直接终止

            # 2. 处理响应
            self.setAuthorization(res, lessonId)  # 更新认证信息
            self.lesson_info(lessonId)  # 获取课程详细信息

            # 3. 解析响应数据
            try:
                self.lessonIdDict[lessonId]['Auth'] = res.json()['data']['lessonToken']
                self.lessonIdDict[lessonId]['userid'] = res.json()['data']['identityId']
            except Exception as e:
                # 数据解析失败时设置默认值
                self.lessonIdDict[lessonId]['Auth'] = ''
                self.lessonIdDict[lessonId]['userid'] = ''

            # 4. 判断签到结果
            checkin_status = res.json().get('msg', '')
            if checkin_status == 'OK':
                # 签到成功
                self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 签到成功")
            elif checkin_status == 'LESSON_END':
                # 课程已结束
                self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 课程已结束")
            else:
                # 其他异常情况
                self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 签到失败")

    def fetch_presentation(self, lessonId):
        url = f"https://{domain}/api/v3/lesson/presentation/fetch?presentation_id={self.lessonIdDict[lessonId]['presentation']}"
        headers = {
            "referer": f"https://{domain}/lesson/fullscreen/v3/{lessonId}?source=5",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "cookie": self.cookie,
            "Authorization": self.lessonIdDict[lessonId]['Authorization']
        }
        res = requests.get(url, headers=headers, timeout=timeout)
        self.setAuthorization(res, lessonId)
        info = res.json()
        slides = info['data']['slides']  # 获得幻灯片列表
        self.lessonIdDict[lessonId]['problems'] = {}
        self.lessonIdDict[lessonId]['covers'] = [slide['index'] for slide in slides if slide.get('cover') is not None]
        for slide in slides:
            if slide.get("problem") is not None:
                self.lessonIdDict[lessonId]['problems'][slide['id']] = slide['problem']
                self.lessonIdDict[lessonId]['problems'][slide['id']]['index'] = slide['index']
                if slide['problem']['body'] == '':
                    shapes = slide.get('shapes', [])
                    if shapes:
                        min_left_item = min(shapes, key=lambda item: item.get('Left', 9999999))
                        if min_left_item != 9999999 and min_left_item.get('Text') is not None:
                            self.lessonIdDict[lessonId]['problems'][slide['id']]['body'] = min_left_item['Text']
                        else:
                            self.lessonIdDict[lessonId]['problems'][slide['id']]['body'] = '未知问题'
                    else:
                        self.lessonIdDict[lessonId]['problems'][slide['id']]['body'] = '未知问题'

                if self.lessonIdDict[lessonId]['problems'][slide['id']]['problemType'] == 5:
                    if self.lessonIdDict[lessonId]['problems'][slide['id']]['answers'] in [[], None, 'null'] and not \
                            self.lessonIdDict[lessonId]['problems'][slide['id']]['result'] in [[], None, 'null']:
                        yuketang.shared_answers[slide['id']] = self.lessonIdDict[lessonId]['problems'][slide['id']][
                            'result']
                elif self.lessonIdDict[lessonId]['problems'][slide['id']]['problemType'] == 4:
                    num_blanks = len(self.lessonIdDict[lessonId]['problems'][slide['id']]['blanks'])
                    if not check_answers_in_blanks(self.lessonIdDict[lessonId]['problems'][slide['id']]['answers'],
                                                   num_blanks):
                        if check_answers_in_blanks(self.lessonIdDict[lessonId]['problems'][slide['id']]['result'],
                                                   num_blanks):
                            yuketang.shared_answers[slide['id']] = self.lessonIdDict[lessonId]['problems'][slide['id']][
                                'result']
                else:
                    if not check_answers_in_options(self.lessonIdDict[lessonId]['problems'][slide['id']]['answers'],
                                                    self.lessonIdDict[lessonId]['problems'][slide['id']][
                                                        'options']) and check_answers_in_options(
                        self.lessonIdDict[lessonId]['problems'][slide['id']]['result'],
                        self.lessonIdDict[lessonId]['problems'][slide['id']]['options']) and not \
                            self.lessonIdDict[lessonId]['problems'][slide['id']]['result'] in [[], None, 'null']:
                        yuketang.shared_answers[slide['id']] = self.lessonIdDict[lessonId]['problems'][slide['id']][
                            'result']
        if self.lessonIdDict[lessonId]['problems'] == {}:
            self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n问题列表: 无")
        else:
            self.msgmgr.sendMsg(
                f"{self.lessonIdDict[lessonId]['header']}\n{format_json_to_text(self.lessonIdDict[lessonId]['problems'], self.lessonIdDict[lessonId].get('unlockedproblem', []))}")
        folder_path = lessonId
        asyncio.create_task(self.download_presentation(slides, folder_path, lessonId))

        async def fetch_presentation_background():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, clear_folder, folder_path)
            await loop.run_in_executor(None, download_images_to_folder, slides, folder_path)
            output_pdf_path = os.path.join(folder_path,
                                           f"{self.lessonIdDict[lessonId]['classroomName']}-{self.lessonIdDict[lessonId]['title']}.pdf")
            await loop.run_in_executor(None, images_to_pdf, folder_path, output_pdf_path)
            if os.path.exists(output_pdf_path):
                try:
                    self.msgmgr.sendFile(output_pdf_path)
                except Exception as e:
                    self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: PPT推送失败")
            else:
                self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 没有PPT")
            if self.ppt:
                asyncio.create_task(fetch_presentation_background())

    async def answer(self, lessonId):
        url = f"https://{domain}/api/v3/lesson/problem/answer"
        headers = {
            "referer": f"https://{domain}/lesson/fullscreen/v3/{lessonId}?source=5",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "cookie": self.cookie,
            "Content-Type": "application/json",
            "Authorization": self.lessonIdDict[lessonId]['Authorization']
        }

        data = {
            "dt": int(time.time() * 1000),
            "problemId": self.lessonIdDict[lessonId]['problemId'],
            "problemType": self.lessonIdDict[lessonId]['problems'][self.lessonIdDict[lessonId]['problemId']][
                'problemType'],
            "result": self.lessonIdDict[lessonId]['problems'][self.lessonIdDict[lessonId]['problemId']]['answers']
        }
        try:
            res = requests.post(url=url, headers=headers, json=data, timeout=timeout)
        except Exception as e:
            return
        self.setAuthorization(res, lessonId)
        self.msgmgr.sendMsg(
            f"{self.lessonIdDict[lessonId]['header']}\nPPT: 第{self.lessonIdDict[lessonId]['problems'][self.lessonIdDict[lessonId]['problemId']]['index']}页\n问题: {self.lessonIdDict[lessonId]['problems'][self.lessonIdDict[lessonId]['problemId']]['body']}\n提交答案: {self.lessonIdDict[lessonId]['problems'][self.lessonIdDict[lessonId]['problemId']]['answers']}")

    async def ws_controller(self, func, *args, retries=3, delay=10):
        attempt = 0
        while attempt <= retries:
            try:
                await func(*args)
                return  # 如果成功就直接返回
            except Exception as e:
                print(traceback.format_exc())
                attempt += 1
                if attempt <= retries:
                    await asyncio.sleep(delay)
                    print(f"出现异常, 尝试重试 ({attempt}/{retries})")

    # WebSocket请求二维码
    async def ws_login(self):
        uri = f"wss://{domain}/wsapp/"
        async with websockets.connect(uri, ping_timeout=180, ping_interval=5) as websocket:
            # 发送 "hello" 消息以建立连接
            hello_message = {
                "op": "requestlogin",
                "role": "web",
                "version": 1.4,
                "type": "qrcode",
                "from": "web"
            }
            await websocket.send(json.dumps(hello_message))
            server_response = await recv_json(websocket)
            qrcode_url = server_response['ticket']  # 服务器响应中返回一个 ticket 字段，该字段是二维码图片的 URL
            download_qrcode(qrcode_url, self.name)  # 通过 download_qrcode 函数下载二维码图片并保存为本地文件
            self.msgmgr.sendImage(f"{self.name}qrcode.jpg")  # 发送二维码图片
            # 扫码触发服务器回调，服务器返回的 UserID 和 Auth 用于后续的登录验证
            server_response = await asyncio.wait_for(recv_json(websocket), timeout=60)
            self.weblogin(server_response['UserID'], server_response['Auth'])

    async def countdown(self, limit):
        try:
            # 等待 limit 秒，或者事件被触发以取消倒计时
            await asyncio.wait_for(self.stop_event.wait(), timeout=limit)
        except asyncio.TimeoutError:
            # 超时表示 limit 时间到了，倒计时正常结束
            self.stop_event.set()
            self.msgmgr.sendMsg(f"问题正常结束")
        else:
            # 如果事件触发，表示提前结束
            self.msgmgr.sendMsg(f"问题已提前结束")

    async def listen_for_problemfinished(self, lessonId, limit):
        # 监听 problemfinished 的消息
        while not self.stop_event.is_set():
            try:
                server_response = await asyncio.wait_for(recv_json(self.lessonIdDict[lessonId]['websocket']),
                                                         timeout=limit)
                if server_response['op'] == "problemfinished":
                    self.stop_event.set()
                    break
            except asyncio.TimeoutError:
                break
            except Exception as e:
                self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 连接断开")
                break

    async def download_presentation(self, slides, folder_path, lessonId):
        await asyncio.get_event_loop().run_in_executor(None, clear_folder, folder_path)
        await asyncio.get_event_loop().run_in_executor(None, download_images_to_folder, slides, folder_path)
        output_pdf_path = os.path.join(folder_path,
                                       f"{self.lessonIdDict[lessonId]['classroomName']}-{self.lessonIdDict[lessonId]['title']}.pdf")
        await asyncio.get_event_loop().run_in_executor(None, images_to_pdf, folder_path, output_pdf_path)
        if os.path.exists(output_pdf_path):
            self.msgmgr.sendFile(output_pdf_path)
        else:
            self.msgmgr.sendMsg(f"PPT下载失败：未找到文件")

    async def receive_messages(self, lessonId):
        await self.pull_probleminfo(lessonId)
        while not self.stop_event.is_set():
            try:
                server_response = await recv_json(self.lessonIdDict[lessonId]['websocket'])
            except Exception as e:
                self.msgmgr.sendMsg(f"{self.lessonIdDict[lessonId]['header']}\n消息: 连接断开")
                break
            op = server_response['op']
            if op == "probleminfo":
                limit = server_response.get('limit')  # 检查是否有 limit 值
                if limit is not None and limit > 0:
                    self.msgmgr.sendMsg(f"问题开始，倒计时 {limit} 秒")
                    await asyncio.gather(
                        self.countdown(limit),  # 倒计时任务
                        self.listen_for_problemfinished(lessonId, limit)  # 监听 "problemfinished" 任务
                    )
                    break
                else:
                    self.msgmgr.sendMsg(f"问题无倒计时")
            if op == "problemfinished":
                self.stop_event.set()
                self.msgmgr.sendMsg(f"问题已结束")
                break

    async def fetch_answers(self, lessonId):
        while not self.stop_event.is_set():
            # 获取幻灯片信息，处理可能的异常
            self.fetch_problems(lessonId)
            await asyncio.sleep(2)

            # 检查当前问题的答案是否存在，如果存在则提交
            if self.lessonIdDict[lessonId]['problems'][self.lessonIdDict[lessonId]['problemId']].get('answers'):
                await self.answer(lessonId)
                self.stop_event.set()
                break  # 提交答案后退出循环

    async def pull_probleminfo(self, lessonId):
        # 构造要发送的消息
        probleminfo_message = {
            "op": "probleminfo",
            "lessonid": lessonId,
            "problemid": self.lessonIdDict[lessonId]['problemId'],
            "msgid": self.lessonIdDict[lessonId]['msgid']
        }

        # 发送消息到 WebSocket
        await self.lessonIdDict[lessonId]['websocket'].send(json.dumps(probleminfo_message))
        # 递增 msgid，确保每条消息的唯一性
        self.lessonIdDict[lessonId]['msgid'] += 1

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
