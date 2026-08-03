import os
import time
import requests
from datetime import datetime, date, timedelta

# 引入 app.py 中的抓取和生成逻辑
from app import run_automation_web, generate_markdown

# ==================== 1. 配置参数（优先从 GitHub 环境变量读取） ====================
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "你的PushPlus_Token") 
IREAD_USER = os.environ.get("IREAD_USER", "你的全阅读账号")
IREAD_PWD = os.environ.get("IREAD_PWD", "你的全阅读密码")

# 班级考核标准配置（根据你的实际班级修改）
CLASS_RULES_CONFIG = {
    "康乐E4": {"listen": 60, "anim": 15, "books": 2},
    "康乐K11": {"listen": 60, "anim": 15, "books": 2},
    "康乐K24": {"listen": 60, "anim": 15, "books": 2},
    "康乐K31": {"listen": 60, "anim": 15, "books": 2},
}

# 英文名映射配置（如果没有映射可以留空）
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
        "template": "markdown"  # 使用 Markdown 保持清晰排版
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
class DummyStatus:
    """模拟 Streamlit 的 status 占位符，以便在终端或日志中打印信息"""
    def info(self, msg): print(f"[INFO] {msg}")
    def success(self, msg): print(f"[SUCCESS] {msg}")
    def warning(self, msg): print(f"[WARN] {msg}")
    def error(self, msg): print(f"[ERROR] {msg}")

def execute_daily_report():
    print(f"\n==================== ⏰ 自动打卡任务开始 [{datetime.now()}] ====================")
    status = DummyStatus()
    
    # 🎯 计算并获取【昨天】的日期
    yesterday = date.today() - timedelta(days=1)
    
    try:
        # 执行抓取，将 report_type 设为 "自定义"，并将开始和结束都设为【昨天】
        report_text = run_automation_web(
            username=IREAD_USER,
            password=IREAD_PWD,
            report_type="自定义",
            start_date=yesterday,
            end_date=yesterday,
            class_rules_config=CLASS_RULES_CONFIG,
            name_maps_config=NAME_MAPS_CONFIG,
            default_rule=DEFAULT_RULE,
            status_placeholder=status
        )
        
        if report_text and report_text.strip():
            # 拼接微信推送标题（显示为昨天的日期）
            title = f"📚 全阅读学情打卡报告 ({yesterday.strftime('%m月%d日')})"
            
            # 发送到微信
            send_to_wechat(title, report_text)
        else:
            print("⚠️ 未获取到有效报告，跳过微信推送。")
            
    except Exception as e:
        error_msg = f"❌ 今日定时任务运行失败：{str(e)}"
        print(error_msg)
        # 抓取失败时也发条通知提醒你检查
        send_to_wechat("⚠️ 全阅读自动打卡报错提醒", error_msg)


# ==================== 4. 主入口 ====================
if __name__ == "__main__":
    execute_daily_report()
