import re
import requests
import traceback
from datetime import date, timedelta

DEFAULT_TEMPLATE = """📌 {class_name} {report_type}（{date_title}）

🌟 【听音&动画双达标】({both_count}人)：
{both_list}

🎵 【仅听音达标】({listen_only_count}人)：
{listen_only_list}

📺 【仅动画达标】({anim_only_count}人)：
{anim_only_list}

📖 【绘本达标】({books_count}人)：
{books_list}

❌ 【未达标/未打卡】({none_count}人)：
{none_list}

--------------------
💡 达标标准：每日听音 ≥ {target_listen}分钟，每日动画 ≥ {target_anim}分钟，绘本 ≥ {target_books}本。"""

DEFAULT_MATRIX_TEMPLATE = """❤️ {date_title} 全阅读打卡 ❤️

{matrix}

--------------------
📊 【学情统计】
• 班级总人数：{total_students} 人
• 全勤全达标（皇冠👑）：{full_attendance_count} 人
• 本阶段打卡率：{attendance_rate}%

💡 提醒：昨天未打卡100%的小朋友尽快补上~，完成百分百💯的小朋友很棒哦[加油][加油][加油]学习要趁早，打卡不能少"""

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

def format_student_name(raw_name, eng_name):
    if not raw_name:
        return ""
    raw_name = str(raw_name).strip()
    if not eng_name:
        return raw_name
    eng_name = str(eng_name).strip()
    if eng_name.lower() in raw_name.lower():
        return raw_name
    return f"{raw_name}({eng_name})"

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
            res_json = resp.json()
            data = res_json.get("data", {})
            token = data.get("token") if isinstance(data, dict) else res_json.get("token")
            if token:
                return token, None
            return None, res_json.get("message") or res_json.get("msg") or "未获取到 Token"
        return None, f"登录异常({resp.status_code})"
    except Exception as e:
        return None, str(e)

def fetch_data_via_api(auth_token, report_type, start_date, end_date, class_rules_config, name_maps_config, default_rule, template_str, mode="traditional", emoji_config=None):
    if emoji_config is None:
        emoji_config = {"full": "🍓", "part": "✅", "zero": "🚫", "badge": "✔️"}

    clean_token = auth_token.strip()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "Token": clean_token,
        "Client-Type": "BROWSER"
    }

    classes_url = "https://v2.ireadabc.com/api/teacher/classes/page/all"
    
    try:
        resp = requests.get(classes_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None, f"Token 失效或服务器错误 (状态码: {resp.status_code})"
            
        res_json = resp.json()
        raw_data = res_json.get("data", [])
        
        classes_data = []
        if isinstance(raw_data, dict):
            classes_data = raw_data.get("rows", []) or raw_data.get("list", []) or raw_data.get("classes", [])
        elif isinstance(raw_data, list):
            classes_data = raw_data
            
        if not classes_data and isinstance(res_json, list):
            classes_data = res_json

        if not classes_data:
            return None, "未能获取到班级列表，请确认 Token 是否正确"

    except Exception as e:
        traceback.print_exc()
        return None, f"请求班级列表异常: {str(e)}"

    reports_dict = {}

    try:
        # 📅 矩阵日历模式
        if mode == "matrix":
            today = date.today()
            d_start = today - timedelta(days=today.weekday()) # 本周一
            days_to_fetch = min(7, (today - d_start).days + 1)
            d_end = d_start + timedelta(days=days_to_fetch - 1)
            date_title = f"{d_start.month}.{d_start.day}--{d_end.month}.{d_end.day}"

            for item in classes_data:
                class_id = str(item.get("id") or item.get("class_id") or item.get("classId"))
                class_name = item.get("class_name") or item.get("name") or item.get("className") or f"班级_{class_id}"
                
                if class_rules_config and class_name not in class_rules_config:
                    continue

                base_rule = class_rules_config.get(class_name, default_rule)
                matched_map = name_maps_config.get(class_name, "")
                class_mapping = parse_name_map(matched_map)

                all_days_students_map = {}

                for day_idx in range(days_to_fetch):
                    curr_date = (d_start + timedelta(days=day_idx)).strftime("%Y-%m-%d")
                    stats_url = f"https://v2.ireadabc.com/api/v3/reports/statistics/class/{class_id}"
                    
                    stat_resp = requests.get(stats_url, headers=headers, params={"start": curr_date, "end": curr_date}, timeout=15)
                    if stat_resp.status_code == 200:
                        s_json = stat_resp.json()
                        students_raw = s_json.get("data", []) if isinstance(s_json, dict) else s_json
                        if isinstance(students_raw, dict):
                            students_raw = students_raw.get("rows", []) or students_raw.get("students", []) or students_raw.get("list", [])

                        for s in students_raw:
                            raw_name = s.get("name") or s.get("student_name") or s.get("studentName") or ""
                            if not raw_name:
                                continue
                            clean_n = re.sub(r'[a-zA-Z\s]', '', raw_name)
                            eng_name = class_mapping.get(clean_n, class_mapping.get(raw_name, ""))
                            display_name = format_student_name(raw_name, eng_name)

                            if display_name not in all_days_students_map:
                                all_days_students_map[display_name] = []

                            listen = clean_num(s.get("listen") or s.get("audio_time") or s.get("listenTime") or 0)
                            anim = clean_num(s.get("animation") or s.get("anim") or s.get("animTime") or 0)
                            books = clean_num(s.get("grading") or s.get("read") or s.get("booksCount") or 0)

                            if listen >= base_rule["listen"] and anim >= base_rule["anim"] and books >= base_rule["books"]:
                                emoji = emoji_config.get("full", "🍓")
                            elif listen == 0 and anim == 0 and books == 0:
                                emoji = emoji_config.get("zero", "🚫")
                            else:
                                emoji = emoji_config.get("part", "✅")
                            
                            all_days_students_map[display_name].append(emoji)

                matrix_lines = []
                total_students = len(all_days_students_map)
                full_attendance_count = 0

                for s_name, emojis in all_days_students_map.items():
                    while len(emojis) < days_to_fetch:
                        emojis.append(emoji_config.get("zero", "🚫"))
                        
                    line = f"{''.join(emojis)}  {s_name}"
                    full_count_in_row = emojis.count(emoji_config.get("full", "🍓"))
                    
                    if days_to_fetch > 0 and full_count_in_row == days_to_fetch:
                        full_attendance_count += 1
                        if emoji_config.get("badge"):
                            line += f" {emoji_config.get('badge')}"
                    matrix_lines.append(line)

                attendance_rate = round((full_attendance_count / total_students * 100), 1) if total_students > 0 else 0.0

                reports_dict[class_name] = template_str.format(
                    date_title=date_title,
                    matrix="\n".join(matrix_lines) if matrix_lines else "（暂无打卡数据）",
                    total_students=total_students,
                    full_attendance_count=full_attendance_count,
                    attendance_rate=attendance_rate
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
            class_id = str(item.get("id") or item.get("class_id") or item.get("classId"))
            class_name = item.get("class_name") or item.get("name") or item.get("className") or f"班级_{class_id}"
            
            if class_rules_config and class_name not in class_rules_config:
                continue

            stats_url = f"https://v2.ireadabc.com/api/v3/reports/statistics/class/{class_id}"
            stat_resp = requests.get(stats_url, headers=headers, params={"start": s_date, "end": e_date}, timeout=15)

            if stat_resp.status_code == 200:
                s_json = stat_resp.json()
                students_raw = s_json.get("data", []) if isinstance(s_json, dict) else s_json
                if isinstance(students_raw, dict):
                    students_raw = students_raw.get("rows", []) or students_raw.get("students", []) or students_raw.get("list", [])

                students_data = [{
                    "name": s.get("name") or s.get("student_name") or s.get("studentName") or "",
                    "listen": s.get("listen") or s.get("audio_time") or s.get("listenTime") or 0,
                    "anim": s.get("animation") or s.get("anim") or s.get("animTime") or 0,
                    "books": s.get("grading") or s.get("read") or s.get("booksCount") or 0
                } for s in students_raw]

                base_rule = class_rules_config.get(class_name, default_rule)
                matched_rule = {k: v * days_count for k, v in base_rule.items()}
                matched_map = name_maps_config.get(class_name, "")
                class_mapping = parse_name_map(matched_map)

                both, listen_only, anim_only, books_list_group, none = [], [], [], [], []
                
                for student in students_data:
                    raw_name = student["name"]
                    if not raw_name:
                        continue
                    clean_n = re.sub(r'[a-zA-Z\s]', '', raw_name)
                    eng_name = class_mapping.get(clean_n, class_mapping.get(raw_name, ""))
                    display_name = format_student_name(raw_name, eng_name)

                    listen = clean_num(student["listen"])
                    anim = clean_num(student["anim"])
                    books = clean_num(student["books"])

                    is_listen = listen >= matched_rule["listen"]
                    is_anim = anim >= matched_rule["anim"]
                    is_books = books >= matched_rule["books"]

                    if is_listen and is_anim:
                        both.append(display_name)
                    elif is_listen:
                        listen_only.append(display_name)
                    elif is_anim:
                        anim_only.append(display_name)
                    else:
                        none.append(display_name)

                    if is_books:
                        books_list_group.append(display_name)

                reports_dict[class_name] = template_str.format(
                    class_name=class_name,
                    report_type=report_type,
                    date_title=date_title,
                    target_listen=base_rule["listen"],
                    target_anim=base_rule["anim"],
                    target_books=base_rule["books"],
                    both_count=len(both),
                    both_list="、".join(both) if both else "无",
                    listen_only_count=len(listen_only),
                    listen_only_list="、".join(listen_only) if listen_only else "无",
                    anim_only_count=len(anim_only),
                    anim_only_list="、".join(anim_only) if anim_only else "无",
                    books_count=len(books_list_group),
                    books_list="、".join(books_list_group) if books_list_group else "无",
                    none_count=len(none),
                    none_list="、".join(none) if none else "无"
                )

        return reports_dict, None
    except Exception as e:
        traceback.print_exc()
        return None, str(e)
