import os
from datetime import datetime, timedelta
from iread_core import run_automation

if __name__ == "__main__":
    username = os.environ.get("IREAD_USER")
    password = os.environ.get("IREAD_PWD")
    pushplus_token = os.environ.get("PUSHPLUS_TOKEN")

    if not username or not password:
        print("错误: 未检测到环境变量 IREAD_USER 或 IREAD_PWD")
        exit(1)

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"开始执行定时任务，统计日期: {yesterday}")

    result = run_automation(
        username=username,
        password=password,
        pushplus_token=pushplus_token,
        target_date=yesterday
    )
    print(f"定时任务执行完成: {result}")
