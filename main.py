# 1. 引入Python内置的异步编程库
import asyncio
# 2. 从自定义模块导入用户管理类
from user_manager import UserManager

if __name__ == "__main__":  # 3. 脚本入口判断
    async def main():     # 4. 定义异步主函数
        user_manager = UserManager()    # 5. 初始化用户管理器
        
        # 6. 启动用户管理任务（协程）
        await user_manager.start_users()

    # 使用 asyncio.run 来启动事件循环并运行主协程
    asyncio.run(main())