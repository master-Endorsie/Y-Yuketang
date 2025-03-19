import asyncio
import logging
import sys
import os
from user_manager import UserManager


def setup_logging():
    """配置日志记录"""
    log_file = "Y-Yuketang.log"

    # 确定日志路径：打包后使用可执行文件目录，否则使用当前目录
    if getattr(sys, 'frozen', False):
        log_dir = os.path.dirname(sys.executable)
    else:
        log_dir = os.getcwd()

    log_path = os.path.join(log_dir, log_file)

    # 配置日志格式（文件和控制台）
    logging.basicConfig(
        filename=log_path,
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filemode='w'  # 覆盖模式，每次运行清空日志
    )
    # 添加控制台输出（显示错误信息）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logging.getLogger().addHandler(console_handler)


async def main():
    """主异步函数"""
    user_manager = UserManager()
    await user_manager.start_users()


if __name__ == "__main__":
    try:
        setup_logging()
        logging.info("程序启动...")

        # 运行异步主函数，并捕获所有异常
        asyncio.run(main())

    except Exception as e:
        logging.exception("程序发生致命错误！")
        logging.error(f"错误类型: {type(e).__name__}")
        logging.error(f"错误信息: {str(e)}")

        # 防止窗口立即关闭，提示用户查看日志
        print("\n程序已崩溃！请查看日志文件：")
        print(f"日志路径：{os.path.abspath('yuketang-autobot.log')}")
        input("按任意键退出...")
