import re
import requests
import traceback
from datetime import date, timedelta

# 💡 完美适配你要求的传统汇报模板格式
DEFAULT_TEMPLATE = """[以下为{date_title}的打卡情况]

🏆 {class_name}

🌟 【今日光荣榜】
{glory_list}

💪 【再努努力】
{effort_list}

⏰ 【该起床打卡啦】
{zero_list}"""

# 💡 干净无重复的矩阵模板
DEFAULT_MATRIX_TEMPLATE = """❤️ {date_title} 全阅读打卡 ❤️

{matrix}

--------------------
{stats}

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
            days_to_fetch = max(1, (end_date - start_date).days + 1)
            date_title = f"{start_date.month}.{start_date.day}--{end_date.month}.{end_date.day}"

            for item in classes_data:
                class_id = str(item.get("id") or item.get("class_id") or item.get("classId"))
                class_name = item.get("class_name") or item.get("name") or item.get("className") or f"班级_{class_id}"
                
                base_rule = class_rules_config.get(class_name, default_rule)
                matched_map = name_maps_config.get(class_name, "")
                class_mapping = parse_name_map(matched_map)

                all_days_students_map = {}

                # 按天严格遍历从 start_date 到 end_date (昨天)
                for day_idx in range(days_to_fetch):
                    curr_date = (start_date + timedelta(days=day_idx)).strftime("%Y-%m-%d")
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
                full_attendance_count = 0  # 每天都有打卡
                effort_count = 0           # 有打卡但有断开
                zero_attendance_count = 0  # 完全没打卡

                full_icon = emoji_config.get("full", "🍓")
                zero_icon = emoji_config.get("zero", "🚫")

                for s_name, emojis in all_days_students_map.items():
                    while len(emojis) < days_to_fetch:
                        emojis.append(zero_icon)
                        
                    line = f"{''.join(emojis)}  {s_name}"
                    
                    full_count_in_row = emojis.count(full_icon)
                    zero_count_in_row = emojis.count(zero_icon)
                    
                    # 💡 依照新规则判定统计人数：
                    # 1. 未打卡提醒：完全没打卡（全都是 zero_icon）
                    if zero_count_in_row == days_to_fetch:
                        zero_attendance_count += 1
                    # 2. 全勤达标：只要每天都有打卡（没有一天是 zero_icon）
                    elif zero_count_in_row == 0:
                        full_attendance_count += 1
                        
                        # 💡 勋章/奖杯标记：只有“每天都完全达标（全是🍓）”的人才有！
                        if full_count_in_row == days_to_fetch and emoji_config.get("badge"):
                            line += f" {emoji_config.get('badge')}"
                    # 3. 持续加油：有打卡也有没打卡（夹杂着 zero_icon）
                    else:
                        effort_count += 1

                    matrix_lines.append(line)

                attendance_rate = round((full_attendance_count / total_students * 100), 1) if total_students > 0 else 0.0

                # 💡 组装符合新逻辑的学情统计汇总文案
                stats_text = f"""📊 学情统计汇总：
🏆 全勤达标：{full_attendance_count} 人 ({attendance_rate}%)
💪 持续加油：{effort_count} 人
⚠️ 未打卡提醒：{zero_attendance_count} 人"""

                if "{stats}" in template_str:
                    curr_matrix_template = template_str
                else:
                    curr_matrix_template = template_str + "\n\n--------------------\n{stats}"

                reports_dict[class_name] = curr_matrix_template.format(
                    date_title=date_title,
                    matrix="\n".join(matrix_lines) if matrix_lines else "（暂无打卡数据）",
                    total_students=total_students,
                    full_attendance_count=full_attendance_count,
                    attendance_rate=attendance_rate,
                    stats=stats_text 
                )

            return reports_dict, None

        # 📋 传统文字分组模式
        s_date, e_date = start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
        days_count = max(1, (end_date - start_date).days + 1)
        
        if s_date == e_date:
            date_title = start_date.strftime("%m月%d日")
        else:
            date_title = f"{s_date}至{e_date}"

        for item in classes_data:
            class_id = str(item.get("id") or item.get("class_id") or item.get("classId"))
            class_name = item.get("class_name") or item.get("name") or item.get("className") or f"班级_{class_id}"
            
            base_rule = class_rules_config.get(class_name, default_rule)
            matched_rule = {k: v * days_count for k, v in base_rule.items()}
            matched_map = name_maps_config.get(class_name, "")
            class_mapping = parse_name_map(matched_map)

            stats_url = f"https://v2.ireadabc.com/api/v3/reports/statistics/class/{class_id}"
            stat_resp = requests.get(stats_url, headers=headers, params={"start": s_date, "end": e_date}, timeout=15)

            if stat_resp.status_code == 200:
                s_json = stat_resp.json()
                students_raw = s_json.get("data", []) if isinstance(s_json, dict) else s_json
                if isinstance(students_raw, dict):
                    students_raw = students_raw.get("rows", []) or students_raw.get("students", []) or students_raw.get("list", [])

                glory_lines = []
                effort_lines = []
                zero_lines = []

                for s in students_raw:
                    raw_name = s.get("name") or s.get("student_name") or s.get("studentName") or ""
                    if not raw_name:
                        continue
                    clean_n = re.sub(r'[a-zA-Z\s]', '', raw_name)
                    eng_name = class_mapping.get(clean_n, class_mapping.get(raw_name, ""))
                    display_name = format_student_name(raw_name, eng_name)

                    listen = clean_num(s.get("listen") or s.get("audio_time") or s.get("listenTime") or 0)
                    anim = clean_num(s.get("animation") or s.get("anim") or s.get("animTime") or 0)
                    books = clean_num(s.get("grading") or s.get("read") or s.get("booksCount") or 0)

                    target_l = matched_rule["listen"]
                    target_a = matched_rule["anim"]
                    target_b = matched_rule["books"]

                    is_listen = listen >= target_l
                    is_anim = anim >= target_a
                    is_books = books >= target_b

                    # 完全达标 -> 🌟 【今日光荣榜】
                    if is_listen and is_anim and is_books:
                        glory_lines.append(f"{display_name} (听音{listen}min, 动画{anim}min, 绘本{books}本)")
                    # 完全没打卡 -> ⏰ 【该起床打卡啦】
                    elif listen == 0 and anim == 0 and books == 0:
                        zero_lines.append(display_name)
                    # 部分达标 -> 💪 【再努努力】
                    else:
                        diffs = []
                        if not is_listen:
                            diffs.append(f"听音还缺{target_l - listen}min")
                        if not is_anim:
                            diffs.append(f"动画还缺{target_a - anim}min")
                        if not is_books:
                            diffs.append(f"绘本还缺{target_b - books}本")
                        
                        diff_str = ", ".join(diffs)
                        effort_lines.append(f"{display_name}：已达标 (距离全勤还缺：{diff_str})")

                curr_traditional_template = template_str if "{glory_list}" in template_str else DEFAULT_TEMPLATE

                reports_dict[class_name] = curr_traditional_template.format(
                    class_name=class_name,
                    date_title=date_title,
                    glory_list="\n".join(glory_lines) if glory_lines else "无",
                    effort_list="\n".join(effort_lines) if effort_lines else "无",
                    zero_list="\n".join(zero_lines) if zero_lines else "无"
                )

        return reports_dict, None
    except Exception as e:
        traceback.print_exc()
        return None, str(e)
