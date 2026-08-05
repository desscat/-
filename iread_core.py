import requests
from datetime import date, timedelta

# 默认班级规则配置（按需修改）
CLASS_RULES_CONFIG = {
    "你的班级名称1": {"listen": 60, "anim": 15, "books": 2},
    "你的班级名称2": {"listen": 40, "anim": 15, "books": 2},
}

DEFAULT_TEMPLATE = """[以下为{date_title}的打卡情况]

🏆 {class_name}

🌟【今日光荣榜】
{tops}

💪【再努努力】
{mids}

⏰【该起床打卡啦】
{zeros}"""

def auto_login(username, password):
    """登录全阅读获取真实 Token"""
    login_url = "https://v2.ireadabc.com/api/login"
    payload = {"phone": str(username).strip(), "password": str(password).strip()}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json;charset=UTF-8"
    }
    try:
        resp = requests.post(login_url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            if isinstance(data, dict) and data.get("token"):
                return data.get("token"), None
            return None, resp.json().get("message") or "未获取到Token"
        return None, f"登录 HTTP 状态码: {resp.status_code}"
    except Exception as e:
        return None, str(e)

def fetch_data_via_api(auth_token, report_type, class_rules_config):
    """获取打卡数据并生成文本报告"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Token": auth_token.strip(),
        "Client-Type": "BROWSER"
    }
    reports_dict = {}

    try:
        # 1. 获取班级列表
        classes_url = "https://v2.ireadabc.com/api/teacher/classes/page/all" 
        resp = requests.get(classes_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None, f"获取班级失败 ({resp.status_code})"
            
        classes_data = resp.json().get("data", [])
        if isinstance(classes_data, dict):
            classes_data = classes_data.get("rows", []) or classes_data.get("list", [])

        # 2. 时间计算
        yest = date.today() - timedelta(days=1)
        s_date = e_date = yest.strftime("%Y-%m-%d")
        date_title = yest.strftime("%m月%d日")

        # 3. 遍历班级抓取打卡
        for item in classes_data:
            class_id = str(item.get("class_id") or item.get("id"))
            class_name = item.get("class_name") or item.get("name") or f"班级_{class_id}"
            
            stats_url = f"https://v2.ireadabc.com/api/v3/reports/statistics/class/{class_id}"
            stat_resp = requests.get(stats_url, headers=headers, params={"start": s_date, "end": e_date}, timeout=15)

            if stat_resp.status_code == 200:
                students_raw = stat_resp.json().get("data", [])
                if isinstance(students_raw, dict):
                    students_raw = students_raw.get("rows", []) or students_raw.get("students", [])

                rule = class_rules_config.get(class_name, {"listen": 60, "anim": 15, "books": 2})
                
                tops, mids, zeros = [], [], []
                for s in students_raw:
                    name = s.get("name") or s.get("student_name") or "无名"
                    listen = int(s.get("listen") or s.get("audio_time") or 0)
                    anim = int(s.get("animation") or s.get("anim") or 0)
                    books = int(s.get("grading") or s.get("read") or 0)

                    if listen >= rule["listen"] and anim >= rule["anim"] and books >= rule["books"]:
                        tops.append(f"{name} (听音{listen}分, 动画{anim}分, 绘本{books}本)")
                    elif listen == 0 and anim == 0 and books == 0:
                        zeros.append(f"{name}")
                    else:
                        mids.append(f"{name} (听音{listen}/{rule['listen']}分, 动画{anim}/{rule['anim']}分, 绘本{books}/{rule['books']}本)")

                reports_dict[class_name] = DEFAULT_TEMPLATE.format(
                    class_name=class_name,
                    date_title=date_title,
                    tops="\n".join(tops) if tops else "（无）",
                    mids="\n".join(mids) if mids else "（无）",
                    zeros="\n".join(zeros) if zeros else "（无）"
                )

        return reports_dict, None
    except Exception as e:
        return None, str(e)
