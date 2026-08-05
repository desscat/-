import re
import requests
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

提醒：昨天未打卡100%的小朋友尽快补上~，完成百分百💯的小朋友很棒哦[加油][加油][加油]学习要趁早，打卡不能少

--------------------
{stats}"""

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

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Authorization": f"Bearer {auth_token.strip()}"
    }
    reports_dict = {}

    try:
        # 多路径轮询获取班级列表，确保兼容
        classes_data = []
        endpoints = [
            "https://v2.ireadabc.com/api/teacher/classes",
            "https://v2.ireadabc.com/api/classes",
            "https://v2.ireadabc.com/api/teacher/class/list"
        ]
        
        for url in endpoints:
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    res_json = resp.json()
                    temp = res_json.get("data", [])
                    if not temp and isinstance(res_json, list):
                        temp = res_json
                    if isinstance(temp, dict):
                        temp = temp.get("list", []) or temp.get("classes", []) or temp.get("rows", [])
                    if temp:
                        classes_data = temp
                        break
            except:
                continue

        if not classes_data:
            return None, "Token 失效或未能获取到任何班级数据，请检查账号密码"

        # 📅 矩阵日历模式
        if mode == "matrix":
            today = date.today()
            d_start = today - timedelta(days=today.weekday()) # 本周一
            days_to_fetch = min(7, (today - d_start).days + 1)
            d_end = d_start + timedelta(days=days_to_fetch - 1)
            date_title = f"{d_start.month}.{d_start.day}--{d_end.month}.{d_end.day}"

            for item in classes_data:
                class_id = str(item.get("classId") or item.get("class_id") or item.get("id"))
                class_name = item.get("className") or item.get("class_name") or item.get("name") or f"班级_{class_id}"
                
                if class_rules_config and class_name not in class_rules_config:
                    continue

                base_rule = class_rules_config.get(class_name, default_rule)
                matched_map = name_maps_config.get(class_name, "")
                class_mapping = parse_name_map(matched_map)

                all_days_students_map = {}

                # 逐天请求真实详情接口：/api/reports/class/{class_id}/detail/{date}
                for day_idx in range(days_to_fetch):
                    curr_date = (d_start + timedelta(days=day_idx)).strftime("%Y-%m-%d")
                    detail_url = f"https://v2.ireadabc.com/api/reports/class/{class_id}/detail/{curr_date}"
                    
                    det_resp = requests.get(detail_url, headers=headers, timeout=10)
                    if det_resp.status_code == 200:
                        det_json = det_resp.json()
                        st_list = det_json.get("data", [])
                        if not st_list and isinstance(det_json, list):
                            st_list = det_json
                        if isinstance(st_list, dict):
                            st_list = st_list.get("students", []) or st_list.get("list", [])

                        for s in st_list:
                            raw_name = s.get("studentName") or s.get("name", "")
                            if not raw_name:
                                continue
                            clean_n = re.sub(r'[a-zA-Z\s]', '', raw_name)
                            eng_name = class_mapping.get(clean_n, class_mapping.get(raw_name, raw_name))
                            display_name = f"{raw_name}{eng_name}" if not eng_name or eng_name == raw_name else f"{raw_name}({eng_name})"

                            if display_name not in all_days_students_map:
                                all_days_students_map[display_name] = []

                            listen = clean_num(s.get("listenTime") or s.get("listen_time") or 0)
                            anim = clean_num(s.get("animTime") or s.get("anim_time") or 0)
                            books = clean_num(s.get("booksCount") or s.get("books_count") or 0)

                            if listen >= base_rule["listen"] and anim >= base_rule["anim"] and books >= base_rule["books"]:
                                emoji = emoji_config.get("full", "🍓")
                            elif listen == 0 and anim == 0 and books == 0:
                                emoji = emoji_config.get("zero", "🚫")
                            else:
                                emoji = emoji_config.get("part", "✅")
                            
                            all_days_students_map[display_name].append(emoji)

                matrix_lines = []
                for s_name, emojis in all_days_students_map.items():
                    # 补齐不足天数的空白占位
                    while len(emojis) < days_to_fetch:
                        emojis.append(emoji_config.get("zero", "🚫"))
                        
                    line = f"{''.join(emojis)}  {s_name}"
                    if days_to_fetch > 0 and emojis.count(emoji_config.get("full", "🍓")) == days_to_fetch and emoji_config.get("badge"):
                        line += f" {emoji_config.get('badge')}"
                    matrix_lines.append(line)

                reports_dict[class_name] = template_str.format(
                    date_title=date_title,
                    matrix="\n".join(matrix_lines) if matrix_lines else "（暂无打卡数据）",
                    stats=""
                )

            return reports_dict, None

        # 📋 传统文字分组模式
        days_count = 1
        if report_type == "昨日汇报":
            yest = date.today() - timedelta(days=1)
            dates_list = [yest]
            date_title = yest.strftime("%m月%d日")
        elif report_type == "周汇报":
            d_start = date.today() - timedelta(days=date.today().weekday())
            d_end = date.today()
            dates_list = [d_start + timedelta(days=i) for i in range((d_end - d_start).days + 1)]
            date_title = f"{d_start.strftime('%Y-%m-%d')}至{d_end.strftime('%Y-%m-%d')}"
        elif report_type == "月汇报":
            d_start = date.today().replace(day=1)
            d_end = date.today()
            dates_list = [d_start + timedelta(days=i) for i in range((d_end - d_start).days + 1)]
            date_title = f"{d_start.strftime('%Y-%m-%d')}至{d_end.strftime('%Y-%m-%d')}"
        elif report_type == "自定义时间":
            dates_list = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
            date_title = f"{start_date.strftime('%Y-%m-%d')}至{end_date.strftime('%Y-%m-%d')}" if start_date != end_date else start_date.strftime("%m月%d日")
        else:
            yest = date.today() - timedelta(days=1)
            dates_list = [yest]
            date_title = yest.strftime("%m月%d日")

        days_count = max(1, len(dates_list))

        for item in classes_data:
            class_id = str(item.get("classId") or item.get("class_id") or item.get("id"))
            class_name = item.get("className") or item.get("class_name") or item.get("name") or f"班级_{class_id}"
            
            if class_rules_config and class_name not in class_rules_config:
                continue

            base_rule = class_rules_config.get(class_name, default_rule)
            req_listen = base_rule["listen"] * days_count
            req_anim = base_rule["anim"] * days_count
            req_books = base_rule["books"] * days_count
            
            matched_map = name_maps_config.get(class_name, "")
            class_mapping = parse_name_map(matched_map)

            student_aggregated = {}

            for day_dt in dates_list:
                day_str = day_dt.strftime("%Y-%m-%d")
                detail_url = f"https://v2.ireadabc.com/api/reports/class/{class_id}/detail/{day_str}"
                
                det_resp = requests.get(detail_url, headers=headers, timeout=10)
                if det_resp.status_code == 200:
                    det_json = det_resp.json()
                    st_list = det_json.get("data", [])
                    if not st_list and isinstance(det_json, list):
                        st_list = det_json
                    if isinstance(st_list, dict):
                        st_list = st_list.get("students", []) or st_list.get("list", [])

                    for s in st_list:
                        raw_name = s.get("studentName") or s.get("name", "")
                        if not raw_name:
                            continue
                        if raw_name not in student_aggregated:
                            student_aggregated[raw_name] = {"listen": 0, "anim": 0, "books": 0}

                        student_aggregated[raw_name]["listen"] += clean_num(s.get("listenTime") or s.get("listen_time") or 0)
                        student_aggregated[raw_name]["anim"] += clean_num(s.get("animTime") or s.get("anim_time") or 0)
                        student_aggregated[raw_name]["books"] += clean_num(s.get("booksCount") or s.get("books_count") or 0)

            both, listen_only, anim_only, books_list_group, none = [], [], [], [], []

            for raw_name, totals in student_aggregated.items():
                clean_n = re.sub(r'[a-zA-Z\s]', '', raw_name)
                eng_name = class_mapping.get(clean_n, class_mapping.get(raw_name, ""))
                display_name = f"{raw_name}({eng_name})" if eng_name else raw_name

                l_time = totals["listen"]
                a_time = totals["anim"]
                b_cnt = totals["books"]

                is_listen = l_time >= req_listen
                is_anim = a_time >= req_anim
                is_books = b_cnt >= req_books

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
        return None, str(e)
