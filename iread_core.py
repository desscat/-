import re
import requests
from datetime import date, timedelta

DEFAULT_TEMPLATE = """[以下为{date_title}的打卡情况]

🏆 {class_name}

🌟【今日光荣榜】
{tops}

💪【再努努力】
{mids}

⏰【该起床打卡啦】
{zeros}"""

DEFAULT_MATRIX_TEMPLATE = """❤️{date_title} 全阅读打卡❤️

{matrix}"""

def parse_name_map(map_str):
    mapping = {}
    if not map_str:
        return mapping
    pairs = re.split(r'[,，\n]', map_str)
    for pair in pairs:
        if ":" in pair or "：" in pair:
            key, val = re.split(r'[:：]', pair, 1)
            mapping[key.strip()] = val.strip()
    return mapping

def clean_num(text):
    if text is None:
        return 0
    nums = re.findall(r'\d+', str(text))
    return int(nums[0]) if nums else 0

def auto_login(username, password):
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
            return None, resp.json().get("message") or "未获取到 Token"
        return None, f"登录异常({resp.status_code})"
    except Exception as e:
        return None, str(e)

def process_student_data(class_name, name, listen, anim, books, req_listen, req_anim, req_books, name_map_str):
    listen = clean_num(listen)
    anim = clean_num(anim)
    books = clean_num(books)
    
    clean_name = re.sub(r'[a-zA-Z\s]', '', name)
    class_mapping = parse_name_map(name_map_str)
    eng_name = class_mapping.get(clean_name, class_mapping.get(name, name))
    
    if listen >= req_listen and anim >= req_anim and books >= req_books:
        return "TOP", f"{eng_name} (听音{listen}min, 动画{anim}min, 绘本{books}本)"
    
    if listen == 0 and anim == 0 and books == 0:
        return "ZERO", f"{eng_name}"
    
    missing = []
    if listen < req_listen:
        missing.append(f"听音{req_listen - listen}min")
    if anim < req_anim:
        missing.append(f"动画{req_anim - anim}min")
    if books < req_books:
        missing.append(f"绘本{req_books - books}本")
        
    return "MID", f"{eng_name}：已达标 (距离全勤还缺：{', '.join(missing)})"

def fetch_data_via_api(auth_token, report_type, start_date, end_date, class_rules_config, name_maps_config, default_rule, template_str, mode="traditional", emoji_config=None):
    if emoji_config is None:
        emoji_config = {"full": "🍓", "part": "✅", "zero": "🚫", "badge": "✔️"}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Token": auth_token.strip(),
        "Client-Type": "BROWSER"
    }
    reports_dict = {}

    try:
        classes_url = "https://v2.ireadabc.com/api/teacher/classes/page/all" 
        resp = requests.get(classes_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None, f"Token 失效或服务器错误 ({resp.status_code})"
            
        raw_data = resp.json().get("data", [])
        classes_data = raw_data.get("rows", []) if isinstance(raw_data, dict) else raw_data

        # 📅 矩阵日历模式（按本周实际发生天数截断）
        if mode == "matrix":
            today = date.today()
            d_start = today - timedelta(days=today.weekday()) # 本周一
            
            # 动态计算：从周一统计到今天（最多 7 天）
            days_to_fetch = min(7, (today - d_start).days + 1)
            d_end = d_start + timedelta(days=days_to_fetch - 1)
            
            date_title = f"{d_start.month}.{d_start.day}--{d_end.month}.{d_end.day}"

            for item in classes_data:
                class_id = str(item.get("class_id") or item.get("id"))
                class_name = item.get("class_name") or item.get("name") or f"班级_{class_id}"
                
                base_rule = next((class_rules_config[k] for k in class_rules_config if k in class_name or class_name in k), default_rule)
                matched_map = next((name_maps_config[k] for k in name_maps_config if k in class_name or class_name in k), "")
                class_mapping = parse_name_map(matched_map)

                student_matrix = {}

                # 遍历从周一到今天的实际天数
                for day_idx in range(days_to_fetch):
                    curr_date = (d_start + timedelta(days=day_idx)).strftime("%Y-%m-%d")
                    stats_url = f"https://v2.ireadabc.com/api/v3/reports/statistics/class/{class_id}"
                    stat_resp = requests.get(stats_url, headers=headers, params={"start": curr_date, "end": curr_date}, timeout=15)

                    if stat_resp.status_code == 200:
                        s_json = stat_resp.json()
                        students_raw = s_json.get("data", []) if isinstance(s_json, dict) else s_json
                        if isinstance(students_raw, dict):
                            students_raw = students_raw.get("rows", []) or students_raw.get("students", [])

                        for s in students_raw:
                            raw_name = s.get("name") or s.get("student_name") or ""
                            clean_n = re.sub(r'[a-zA-Z\s]', '', raw_name)
                            eng_name = class_mapping.get(clean_n, class_mapping.get(raw_name, raw_name))

                            if eng_name not in student_matrix:
                                student_matrix[eng_name] = []

                            listen = clean_num(s.get("listen") or s.get("audio_time") or 0)
                            anim = clean_num(s.get("animation") or s.get("anim") or 0)
                            books = clean_num(s.get("grading") or s.get("read") or 0)

                            if listen >= base_rule["listen"] and anim >= base_rule["anim"] and books >= base_rule["books"]:
                                emoji = emoji_config.get("full", "🍓")
                            elif listen == 0 and anim == 0 and books == 0:
                                emoji = emoji_config.get("zero", "🚫")
                            else:
                                emoji = emoji_config.get("part", "✅")
                            
                            student_matrix[eng_name].append(emoji)

                matrix_lines = []
                for s_name, emojis in student_matrix.items():
                    line = f"{''.join(emojis)} {s_name}"
                    
                    # 只有统计满7天（到了周末）且全勤时才展示尾巴 Badge
                    if days_to_fetch == 7 and emojis.count(emoji_config.get("full", "🍓")) == 7 and emoji_config.get("badge"):
                        line += f" {emoji_config.get('badge')}"
                    matrix_lines.append(line)

                reports_dict[class_name] = template_str.format(
                    class_name=class_name,
                    date_title=date_title,
                    matrix="\n".join(matrix_lines)
                )

            return reports_dict, None

        # 📋 传统文字分组模式
        days_count = 1
        if report_type == "昨日汇报":
            yest = date.today() - timedelta(days=1)
            s_date = e_date = yest.strftime("%Y-%m-%d")
            date_title = yest.strftime("%m月%d日")
        elif report_type == "周汇报":
            d_start = date.today() - timedelta(days=date.today().weekday())
            d_end = date.today()
            s_date, e_date = d_start.strftime("%Y-%m-%d"), d_end.strftime("%Y-%m-%d")
            date_title = f"{s_date}至{e_date}"
            days_count = (d_end - d_start).days + 1
        elif report_type == "月汇报":
            d_start = date.today().replace(day=1)
            d_end = date.today()
            s_date, e_date = d_start.strftime("%Y-%m-%d"), d_end.strftime("%Y-%m-%d")
            date_title = f"{s_date}至{e_date}"
            days_count = (d_end - d_start).days + 1
        elif report_type == "自定义时间":
            s_date, e_date = start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
            date_title = f"{s_date}至{e_date}" if s_date != e_date else start_date.strftime("%m月%d日")
            days_count = max(1, (end_date - start_date).days + 1)
        else:
            yest = date.today() - timedelta(days=1)
            s_date = e_date = yest.strftime("%Y-%m-%d")
            date_title = yest.strftime("%m月%d日")

        for item in classes_data:
            class_id = str(item.get("class_id") or item.get("id"))
            class_name = item.get("class_name") or item.get("name") or f"班级_{class_id}"
            
            stats_url = f"https://v2.ireadabc.com/api/v3/reports/statistics/class/{class_id}"
            stat_resp = requests.get(stats_url, headers=headers, params={"start": s_date, "end": e_date}, timeout=15)

            if stat_resp.status_code == 200:
                s_json = stat_resp.json()
                students_raw = s_json.get("data", []) if isinstance(s_json, dict) else s_json
                if isinstance(students_raw, dict):
                    students_raw = students_raw.get("rows", []) or students_raw.get("students", [])

                students_data = [{
                    "name": s.get("name") or s.get("student_name") or "",
                    "listen": s.get("listen") or s.get("audio_time") or 0,
                    "anim": s.get("animation") or s.get("anim") or 0,
                    "books": s.get("grading") or s.get("read") or 0
                } for s in students_raw]

                base_rule = next((class_rules_config[k] for k in class_rules_config if k in class_name or class_name in k), default_rule)
                matched_rule = {k: v * days_count for k, v in base_rule.items()}
                matched_map = next((name_maps_config[k] for k in name_maps_config if k in class_name or class_name in k), "")

                tops, mids, zeros = [], [], []
                for student in students_data:
                    status, text = process_student_data(
                        class_name, student['name'], student['listen'], student['anim'], student['books'],
                        matched_rule["listen"], matched_rule["anim"], matched_rule["books"], matched_map
                    )
                    if status == "TOP": tops.append(text)
                    elif status == "MID": mids.append(text)
                    else: zeros.append(text)

                reports_dict[class_name] = template_str.format(
                    class_name=class_name,
                    date_title=date_title,
                    tops="\n".join(tops) if tops else "（暂无）",
                    mids="\n\n".join(mids) if mids else "（无）",
                    zeros="\n\n".join(zeros) if zeros else "（无）"
                )

        return reports_dict, None
    except Exception as e:
        return None, str(e)
