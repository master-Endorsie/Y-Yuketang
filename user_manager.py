import yuketang
import asyncio
import json
import os
from yuketang import ykt_user
from util import logger  # 新增导入语句

current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)
with open('config.json', 'r', encoding='utf-8') as f:
    user_data = json.load(f)


async def ykt_user(ykt):
    while True:
        await ykt.getcookie()
        if ykt.getlesson():
            ykt.lesson_checkin()
            await ykt.lesson_attend()
        await asyncio.sleep(30)


class UserManager:
    def __init__(self):
        logger.info("用户管理器初始化")
        self.users = {}
        self.load_users()

    def load_users(self):
        for user_info in user_data['users']:
            # 为每个用户创建 Yuketang 实例
            name = user_info['name']
            openId = user_info['openId']
            self.users[name] = yuketang.yuketang(name, openId)
            
    async def start_users(self):
        logger.info("启动所有用户任务")
        tasks = []
        for name in self.users:
            tasks.append(asyncio.create_task(ykt_user(self.users[name])))
        await asyncio.gather(*tasks)
