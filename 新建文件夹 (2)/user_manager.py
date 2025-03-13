# 自定义模块
import yuketang 
# 2. 异步编程库，用于并发处理用户任务
import asyncio
# 3. JSON处理库，用于读取配置文件
import json
# 4. 操作系统接口库，用于处理文件路径
import os
# 5. 从yuketang模块导入异步用户处理函数
from yuketang import ykt_user

# 获取当前脚本所在目录路径
current_dir = os.path.dirname(os.path.abspath(__file__))
# __file__ 是Python内置变量，表示当前脚本的相对路径
# abspath 将相对路径转换为绝对路径（例如：将./script.py转为/home/user/project/script.py）
# os.path.abspath(__file__)函数 获取当前脚本的绝对路径
# os.path.dirname(path)函数 从路径中提取目录部分
os.chdir(current_dir)   # 改变当前进程的工作目录

# 7. 读取配置文件中的用户数据
# 'r'：只读模式。
# f 是通过 as 关键字定义的变量名
with open('config.json', 'r', encoding='utf-8') as f: 
    user_data = json.load(f)

class UserManager:  # 8. 用户管理类定义
    def __init__(self):     # 方法体，def定义函数/方法，语法：def 函数名(参数列表):
        self.users = {}     # 存储用户的会话
        self.load_users()   # 自动加载用户数据

    def load_users(self):
        # for循环语法：for variable in iterable:
        # variable: 每次循环时，存储当前元素的临时变量（此处为user_info）
        # iterable: 需要遍历的可迭代对象（此处为user_data['users']，即配置文件中的用户列表）。
        for user_info in user_data['users']:    
            # 为每个用户创建 Yuketang 实例
            name = user_info['name']
            openId = user_info['openId']
            self.users[name] = yuketang.yuketang(name, openId)
            
    async def start_users(self):
        """为每个用户启动 ykt_user 异步任务"""
        tasks = []
        for name in self.users:
            # 从 self.users 字典中获取每个用户的 Yuketang 实例
            ykt_instance = self.users[name]
            # 为每个用户创建一个异步任务，调用 ykt_user 函数
            tasks.append(asyncio.create_task(ykt_user(ykt_instance)))
        
        # 并行执行所有任务
        await asyncio.gather(*tasks)



