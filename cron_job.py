import os
from datetime import datetime, date, timedelta
import requests

# 从独立的纯逻辑核心中导入自动化抓取函数
from iread_core import run_automation

# ==================== 1. 配置参数（优先从 GitHub 环境变量读取） ====================
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "你的PushPlus_Token") 
IREAD_USER = os.environ.get("IREAD_USER", "你的全阅读账号")
IREAD_PWD = os.environ.get("IREAD_PWD", "你的全阅读密码")

# 班级考核标准配置
CLASS_RULES_CONFIG = {
    "康乐E4": {"listen": 40, "anim": 15, "books": 2},
    "康乐K11": {"listen": 60, "anim": 15, "books": 2},
    "康乐K24": {"listen": 60, "anim": 15, "books": 2},
    "康乐K31": {"listen": 60, "anim": 15, "books": 2},
}

# 英文名映射配置
NAME_MAPS_CONFIG = {
    "康乐E4": ""
}

# 通用兜底标准
DEFAULT_RULE = {"listen": 60, "anim": 15, "books": 2}


# ==================== 2. PushPlus 推送函数 ====================
def send_to_wechat(title, content):
    """通过 PushPlus 将打卡报告推送到个人微信"""
    url = "http://www.pushplus.plus/send"
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "markdown" 
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        res_json = response.json()
        if res_json.get("code") == 200:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ 微信推送成功！")
        else:
            print(f"❌ 推送失败，原因：{res_json.get('msg')}")
    except Exception as e:
        print(f"❌ 发送 HTTP 请求报错：{str(e)}")


# ==================== 3. 核心执行逻辑 ====================
def execute_daily_report():
    print(f"\n==================== ⏰ 自动打卡任务开始 [{datetime.now()}] ====================")
    
    # 🎯 计算并获取【昨天】的日期
    yesterday = date.today() - timedelta(days=1)
    
    try:
        # 执行抓取
        report_text = run_automation(
            username=IREAD_USER,
            password=IREAD_PWD,
            start_date=yesterday,
            end_date=yesterday,
            class_rules_config=CLASS_RULES_CONFIG,
            name_maps_config=NAME_MAPS_CONFIG,
            default_rule=DEFAULT_RULE
        )
        
        if report_text and report_text.strip():
            title = f"📚 全阅读学情打卡报告 ({yesterday.strftime('%m月%d日')})"
            send_to_wechat(title, report_text)
        else:
            print("⚠️ 未获取到有效报告，跳过微信推送。")
            
    except Exception as e:
        error_msg = f"❌ 今日定时任务运行失败：{str(e)}"
        print(error_msg)
        send_to_wechat("⚠️ 全阅读自动打卡报错提醒", error_msg)


# ==================== 4. 主入口 ====================
if __name__ == "__main__":
    execute_daily_report()
