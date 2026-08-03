import time
import requests
from datetime import datetime, date, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler

# 引入之前 app.py 中的抓取和生成逻辑
from app import run_automation_web, generate_markdown

# ==================== 1. 配置参数 ====================
# 将这里的配置替换为你自己的真实信息
PUSHPLUS_TOKEN = "8e6def430cef47be99f2a6fe4b5aa2f7"  # 填入第一步获取的 Token
IREAD_USER = "你的全阅读账号"
IREAD_PWD = "你的全阅读密码"

# 班级考核标准配置（根据你的实际班级修改）
CLASS_RULES_CONFIG = {
    "康乐K25": {"listen": 60, "anim": 15, "books": 2},
    # "其他班级": {"listen": 60, "anim": 15, "books": 2}
}

# 英文名映射配置
NAME_MAPS_CONFIG = {
    "康乐K25": "张三:Tom, 李四:Jerry"
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
    """模拟 Streamlit 的 status 占位符，以便在终端打印日志"""
    def info(self, msg): print(f"[INFO] {msg}")
    def success(self, msg): print(f"[SUCCESS] {msg}")
    def warning(self, msg): print(f"[WARN] {msg}")
    def error(self, msg): print(f"[ERROR] {msg}")

def execute_daily_report():
    print(f"\n==================== ⏰ 自动打卡任务开始 [{datetime.now()}] ====================")
    status = DummyStatus()
    
    try:
        # 执行“今日汇报”抓取
        report_text = run_automation_web(
            username=IREAD_USER,
            password=IREAD_PWD,
            report_type="今日汇报",
            start_date=date.today(),
            end_date=date.today(),
            class_rules_config=CLASS_RULES_CONFIG,
            name_maps_config=NAME_MAPS_CONFIG,
            default_rule=DEFAULT_RULE,
            status_placeholder=status
        )
        
        if report_text and report_text.strip():
            # 拼接微信推送标题
            today_str = datetime.now().strftime("%m月%d日")
            title = f"📚 全阅读学情打卡报告 ({today_str})"
            
            # 发送到微信
            send_to_wechat(title, report_text)
        else:
            print("⚠️ 未获取到有效报告，跳过微信推送。")
            
    except Exception as e:
        error_msg = f"❌ 今日定时任务运行失败：{str(e)}"
        print(error_msg)
        # 抓取失败时也发条通知提醒你检查
        send_to_wechat("⚠️ 全阅读自动打卡报错提醒", error_msg)


# ==================== 4. 定时任务调度器 ====================
if __name__ == "__main__":
    scheduler = BlockingScheduler()
    
    # ⏱️ 设置每天晚上 21:00 自动运行（可自行调整 hour 和 minute）
    scheduler.add_job(execute_daily_report, 'cron', hour=21, minute=0)
    
    print("🚀 定时任务服务已启动！")
    print("📅 任务设定：每天 21:00 自动抓取并推送至微信。")
    print("💡 (提示：如果想立即测试一次，可以解除下方 execute_daily_report() 的注释)")
    
    # execute_daily_report() # 取消此行注释即可启动后立即测试一次
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n定时任务已停止。")
