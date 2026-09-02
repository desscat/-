import re
import requests
import traceback
from datetime import date, timedelta

DEFAULT_TEMPLATE = """[以下为{date_title}的打卡情况]

🏆 {class_name}

🌟 【今日光荣榜】
{glory_list}

💪 【再努努力】
{effort_list}

⏰ 【该起床打卡啦】
{zero_list}"""

DEFAULT_MATRIX_TEMPLATE = """❤️ {date_title} 全阅读打卡 ❤️

{matrix}

--------------------
{stats}

💡 提醒：昨天未打卡100%的小朋友尽快补上~，完成百分百💯的小朋友很棒哦[加油][加油][加油]学习要趁早，打卡不能少"""

def parse_name_map(map_str):
    mapping = {}
    if not map_str: return mapping
    for pair in re.split(r'[,，\n]', map_str):
        if ":" in pair or "：" in pair:
            key, val = re.split(r'[:：]', pair, 1)
            mapping[key.strip()] = val.strip()
    return mapping

def clean_num(text):
    nums = re.findall(r'\d+', str(text or 0))
    return int(nums[0]) if nums else 0

def format_student_name(raw_name, eng_name):
    if not raw_name: return ""
    raw_name, eng_name = str(raw_name).strip(), str(eng_name or "").strip()
    return raw_name if not eng_name or eng_name.lower() in raw_name.lower() else f"{raw_name}({eng_name})"

def auto_login(username, password):
    login_url = "https://v2.ireadabc.com/api/login"
    payload = {"phone": str(username).strip(), "password": str(password).strip()}
    headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json;charset=UTF-8"}
    try:
        resp = requests.post(login_url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            res_json = resp.json()
            data = res_json.get("data", {})
            token = data.get("token") if isinstance(data, dict) else res_json.get("token")
            return (token, None) if token else (None, res_json.get("message") or "未获取到 Token")
        return None, f"登录异常({resp.status_code})"
    except Exception as e:
        return None, str(e)

def fetch_data_via_api(auth_token, report_type, start_date, end_date, class_rules_config, name_maps_config, default_rule, template_str, mode="traditional", emoji_config=None):
    if emoji_config is None:
        emoji_config = {"full": "🍓", "part": "✅", "zero": "🚫", "badge": "✔️"}

    headers = {"User-Agent": "Mozilla/5.0", "Token": auth_token.strip(), "Client-Type": "BROWSER"}
    
    try:
        resp = requests.get("https://v2.ireadabc.com/api/teacher/classes/page/all", headers=headers, timeout=15)
        if resp.status_code != 200: return None, f"Token 失效或服务器错误 ({resp.status_code})"
        raw_data = resp.json().get("data", [])
        classes_data = raw_data.get("rows", []) if isinstance(raw_data, dict) else raw_data
        if not classes_data: return None, "未能获取到班级列表"
    except Exception as e:
        return None, f"请求班级列表异常: {str(e)}"

    reports_dict = {}

    if mode == "matrix":
        today = date.today()
        d_start = today - timedelta(days=today.weekday())
        days_to_fetch = min(7, (today - d_start).days + 1)
        date_title = f"{d_start.month}.{d_start.day}--{(d_start + timedelta(days=days_to_fetch - 1)).month}.{(d_start + timedelta(days=days_to_fetch - 1)).day}"

        for item in classes_data:
            class_id = str(item.get("id") or item.get("class_id") or item.get("classId"))
            class_name = item.get("class_name") or item.get("name") or item.get("className") or f"班级_{class_id}"
            base_rule = class_rules_config.get(class_name, default_rule)
            class_mapping = parse_name_map(name_maps_config.get(class_name, ""))

            all_days_students_map, all_days_active_map = {}, {}

            for day_idx in range(days_to_fetch):
                curr_date = (d_start + timedelta(days=day_idx)).strftime("%Y-%m-%d")
                stat_resp = requests.get(f"https://v2.ireadabc.com/api/v3/reports/statistics/class/{class_id}", headers=headers, params={"start": curr_date, "end": curr_date}, timeout=15)
                if stat_resp.status_code == 200:
                    s_json = stat_resp.json()
                    students_raw = s_json.get("data", []) if isinstance(s_json, dict) else s_json
                    if isinstance(students_raw, dict): students_raw = students_raw.get("rows", []) or students_raw.get("students", [])

                    for s in students_raw:
                        raw_name = s.get("name") or s.get("student_name") or s.get("studentName") or ""
                        if not raw_name: continue
                        eng_name = class_mapping.get(re.sub(r'[a-zA-Z\s]', '', raw_name), class_mapping.get(raw_name, ""))
                        display_name = format_student_name(raw_name, eng_name)

                        all_days_students_map.setdefault(display_name, [])
                        all_days_active_map.setdefault(display_name, [])

                        listen = clean_num(s.get("listen") or s.get("audio_time") or s.get("listenTime"))
                        anim = clean_num(s.get("animation") or s.get("anim") or s.get("animTime"))
                        books = clean_num(s.get("grading") or s.get("read") or s.get("booksCount"))

                        is_active_today = (listen + anim + books) > 0
                        all_days_active_map[display_name].append(is_active_today)

                        if listen >= base_rule["listen"] and anim >= base_rule["anim"] and books >= base_rule["books"]:
                            emoji = emoji_config.get("full", "🍓")
                        elif not is_active_today:
                            emoji = emoji_config.get("zero", "🚫")
                        else:
                            emoji = emoji_config.get("part", "✅")
                        all_days_students_map[display_name].append(emoji)

            matrix_lines, full_cnt, part_cnt, zero_cnt = [], 0, 0, 0
            for s_name, emojis in all_days_students_map.items():
                active_days = all_days_active_map[s_name]
                while len(emojis) < days_to_fetch:
                    emojis.append(emoji_config.get("zero", "🚫"))
                    active_days.append(False)

                line = f"{''.join(emojis)}  {s_name}"
                active_days_count = sum(1 for act in active_days if act)

                if active_days_count == days_to_fetch:
                    full_cnt += 1
                    if emoji_config.get("badge"): line += f" {emoji_config.get('badge')}"
                elif active_days_count == 0:
                    zero_cnt += 1
                else:
                    part_cnt += 1
                matrix_lines.append(line)

            total_students = len(all_days_students_map)
            pct = round((full_cnt / total_students * 100)) if total_students > 0 else 0

            stats_text = f"学情统计汇总：\n🌟 全勤达标：{full_cnt} 人（{pct}%）\n💪 持续加油：{part_cnt} 人\n⚠️ 未打卡提醒：{zero_cnt} 人"
            curr_matrix_template = template_str if "{matrix}" in template_str else DEFAULT_MATRIX_TEMPLATE

            reports_dict[class_name] = curr_matrix_template.format(
                date_title=date_title,
                matrix="\n".join(matrix_lines) if matrix_lines else "（暂无打卡数据）",
                total_students=total_students,
                full_attendance_count=full_cnt,
                attendance_rate=pct,
                stats=stats_text 
            )
        return reports_dict, None

    # 传统模式保持原样
    days_count = 1
    yest = date.today() - timedelta(days=1)
    s_date = e_date = yest.strftime("%Y-%m-%d")
    date_title = yest.strftime("%m月%d日")
    if report_type == "周汇报":
        d_start, d_end = date.today() - timedelta(days=date.today().weekday()), date.today()
        s_date, e_date = d_start.strftime("%Y-%m-%d"), d_end.strftime("%Y-%m-%d")
        date_title = f"{s_date}至{e_date}"
        days_count = (d_end - d_start).days + 1
    elif report_type == "自定义时间":
        s_date, e_date = start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
        date_title = f"{s_date}至{e_date}" if s_date != e_date else start_date.strftime("%m月%d日")
        days_count = max(1, (end_date - start_date).days + 1)

    for item in classes_data:
        class_id = str(item.get("id") or item.get("class_id") or item.get("classId"))
        class_name = item.get("class_name") or item.get("name") or item.get("className") or f"班级_{class_id}"
        base_rule = class_rules_config.get(class_name, default_rule)
        matched_rule = {k: v * days_count for k, v in base_rule.items()}
        class_mapping = parse_name_map(name_maps_config.get(class_name, ""))

        stat_resp = requests.get(f"https://v2.ireadabc.com/api/v3/reports/statistics/class/{class_id}", headers=headers, params={"start": s_date, "end": e_date}, timeout=15)
        if stat_resp.status_code == 200:
            s_json = stat_resp.json()
            students_raw = s_json.get("data", []) if isinstance(s_json, dict) else s_json
            if isinstance(students_raw, dict): students_raw = students_raw.get("rows", []) or students_raw.get("students", [])

            glory_lines, effort_lines, zero_lines = [], [], []
            for s in students_raw:
                raw_name = s.get("name") or s.get("student_name") or s.get("studentName") or ""
                if not raw_name: continue
                eng_name = class_mapping.get(re.sub(r'[a-zA-Z\s]', '', raw_name), class_mapping.get(raw_name, ""))
                display_name = format_student_name(raw_name, eng_name)

                listen = clean_num(s.get("listen") or s.get("audio_time") or s.get("listenTime"))
                anim = clean_num(s.get("animation") or s.get("anim") or s.get("animTime"))
                books = clean_num(s.get("grading") or s.get("read") or s.get("booksCount"))

                target_l, target_a, target_b = matched_rule["listen"], matched_rule["anim"], matched_rule["books"]
                is_listen, is_anim, is_books = listen >= target_l, anim >= target_a, books >= target_b

                if is_listen and is_anim and is_books:
                    glory_lines.append(f"{display_name} (听音{listen}min, 动画{anim}min, 绘本{books}本)")
                elif listen == 0 and anim == 0 and books == 0:
                    zero_lines.append(display_name)
                else:
                    diffs = []
                    if not is_listen: diffs.append(f"听音还缺{target_l - listen}min")
                    if not is_anim: diffs.append(f"动画还缺{target_a - anim}min")
                    if not is_books: diffs.append(f"绘本还缺{target_b - books}本")
                    effort_lines.append(f"{display_name}：已达标 (距离全勤还缺：{', '.join(diffs)})")

            curr_traditional_template = template_str if "{glory_list}" in template_str else DEFAULT_TEMPLATE
            reports_dict[class_name] = curr_traditional_template.format(
                class_name=class_name, date_title=date_title,
                glory_list="\n".join(glory_lines) if glory_lines else "无",
                effort_list="\n".join(effort_lines) if effort_lines else "无",
                zero_list="\n".join(zero_lines) if zero_lines else "无"
            )

    return reports_dict, None
