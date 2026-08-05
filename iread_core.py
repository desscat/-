import requests
import json
from datetime import datetime, timedelta

# 各班级考核标准配置（可根据实际情况修改）
CLASS_RULES_CONFIG = {
    "你的班级名称1": {"listen": 60, "anim": 15, "books": 2},
    "你的班级名称2": {"listen": 40, "anim": 15, "books": 2},
}

def login_iread(username, password):
    """登录全阅读获取 Token"""
    url = "https://api.iread.com/v1/user/login"
    payload = {"username": username, "password": password}
    try:
        response = requests.post(url, json=payload, timeout=10)
        res_data = response.json()
        if res_data.get("code") == 200 or "token" in res_data:
            return res_data.get("data", {}).get("token") or res_data.get("token")
    except Exception as e:
        print(f"登录异常: {e}")
    return None

def fetch_class_data(token, class_id, start_date, end_date):
    """获取指定班级的打卡数据"""
    url = f"https://api.iread.com/v1/teacher/stats?class_id={class_id}&start={start_date}&end={end_date}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        return response.json().get("data", [])
    except Exception as e:
        print(f"获取班级数据失败: {e}")
        return []

def send_pushplus(token, title, content):
    """通过 PushPlus 发送微信通知"""
    url = "http://www.pushplus.plus/send"
    data = {
        "token": token,
        "title": title,
        "content": content,
        "template": "markdown"
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        print(f"PushPlus 发送失败: {e}")
        return None

def run_automation(username, password, pushplus_token, target_date=None):
    """执行自动化统计与推送的核心函数"""
    if not target_date:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    token = login_iread(username, password)
    if not token:
        if pushplus_token:
            send_pushplus(pushplus_token, "⚠️ 全阅读打卡提醒报错", f"账号 {username} 登录失败，请检查账号密码。")
        return "登录失败，请检查凭证"

    report_content = f"# 📊 每日打卡统计报告\n**统计日期：** {target_date}\n\n"
    
    for class_name, rules in CLASS_RULES_CONFIG.items():
        report_content += f"### 🏫 班级：{class_name}\n"
        report_content += f"- 听力标准：{rules['listen']}分钟\n"
        report_content += f"- 动画标准：{rules['anim']}分钟\n"
        report_content += f"- 阅读标准：{rules['books']}本\n\n---\n"

    if pushplus_token:
        send_pushplus(pushplus_token, f"【打卡日报】{target_date}", report_content)
    
    return "运行成功并已推送"
