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

def auto_login(username, password):
    url = "https://v2.ireadabc.com/api/login"
    payload = {
        "phone": str(username).strip(),
        "password": str(password).strip()
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None, f"登录接口响应异常 (HTTP {resp.status_code})"
            
        res_json = resp.json()
        token = None
        if isinstance(res_json, dict):
            if "data" in res_json and isinstance(res_json["data"], dict):
                token = res_json["data"].get("token")
            if not token:
                token = res_json.get("token")

        if token:
            return token, None
        else:
            msg = res_json.get("msg") or res_json.get("message") or "登录失败，请检查手机号或密码"
            return None, msg
    except Exception as e:
        return None, f"登录请求发生异常：{str(e)}"

def fetch_data_via_api(token, report_type, start_date, end_date, class_rules, name_maps, default_rule, template_str, mode="traditional", emoji_config=None):
    if mode == "matrix":
        today = date.today()
        s_date = today - timedelta(days=today.weekday())
        e_date = today
    else:
        if report_type == "昨日汇报":
            s_date = date.today() - timedelta(days=1)
            e_date = s_date
        elif report_type == "周汇报":
            today = date.today()
            s_date = today - timedelta(days=today.weekday())
            e_date = today
        elif report_type == "月汇报":
            today = date.today()
            s_date = today.replace(day=1)
            e_date = today
        else:
            s_date, e_date = start_date, end_date

    headers = {
        "Authorization": f"Bearer {token}", 
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        # 1. 获取老师名下的班级列表
        cls_resp = requests.get("https://v2.ireadabc.com/api/teacher/classes", headers=headers, timeout=10)
        if cls_resp.status_code != 200:
            cls_resp = requests.get("https://v2.ireadabc.com/api/classes", headers=headers, timeout=10)
            
        if cls_resp.status_code != 200:
            return None, f"获取班级列表失败 (HTTP {cls_resp.status_code})"
            
        cls_json = cls_resp.json()
        classes_data = cls_json.get("data", [])
        if not classes_data and isinstance(cls_json, list):
            classes_data = cls_json
        if isinstance(classes_data, dict):
            classes_data = classes_data.get("list", []) or classes_data.get("classes", [])

        if not classes_data:
            return None, "未能在该账号下找到任何班级数据"

        parsed_maps = {}
        for c_name, map_str in name_maps.items():
            parsed_maps[c_name] = {}
            if map_str:
                for line in map_str.split("\n"):
                    if ":" in line or "：" in line:
                        line_clean = line.replace("：", ":")
                        parts = line_clean.split(":")
                        if len(parts) == 2:
                            parsed_maps[c_name][parts[0].strip()] = parts[1].strip()

        reports = {}

        for cls_item in classes_data:
            c_name = cls_item.get("className") or cls_item.get("name") or cls_item.get("class_name")
            c_id = cls_item.get("classId") or cls_item.get("id") or cls_item.get("class_id")
            
            if not c_name or not c_id:
                continue
                
            if class_rules and c_name not in class_rules:
                continue

            rule = class_rules.get(c_name, default_rule)
            c_map = parsed_maps.get(c_name, {})

            if mode == "matrix":
                days_count = (e_date - s_date).days + 1
                date_title = f"{s_date.month}.{s_date.day}--{e_date.month}.{e_date.day}"
                
                e_full = emoji_config.get("full", "⭐") if emoji_config else "⭐"
                e_part = emoji_config.get("part", "✨") if emoji_config else "✨"
                e_zero = emoji_config.get("zero", "⚪") if emoji_config else "⚪"
                e_badge = emoji_config.get("badge", "👑") if emoji_config else "👑"

                matrix_lines = []
                # 先拉取每个学生一段日期内的记录汇总或按天循环
                # 这里我们通过循环每一天请求对应日期的 detail 接口来聚合矩阵数据
                all_days_students_map = {} # { student_name: { date_str: {listen, anim, books} } }

                for i in range(days_count):
                    day_dt = s_date + timedelta(days=i)
                    day_str = day_dt.strftime("%Y-%m-%d")
                    
                    detail_url = f"https://v2.ireadabc.com/api/reports/class/{c_id}/detail/{day_str}"
                    det_resp = requests.get(detail_url, headers=headers, timeout=8)
                    if det_resp.status_code == 200:
                        det_json = det_resp.json()
                        st_list = det_json.get("data", [])
                        if not st_list and isinstance(det_json, list):
                            st_list = det_json
                        if isinstance(st_list, dict):
                            st_list = st_list.get("students", []) or st_list.get("list", [])
                        
                        for st in st_list:
                            s_name = st.get("studentName") or st.get("name", "")
                            if not s_name:
                                continue
                            if s_name not in all_days_students_map:
                                all_days_students_map[s_name] = {}
                            
                            all_days_students_map[s_name][day_str] = {
                                "listen": st.get("listenTime") or st.get("listen_time", 0),
                                "anim": st.get("animTime") or st.get("anim_time", 0),
                                "books": st.get("booksCount") or st.get("books_count", 0)
                            }

                if not all_days_students_map:
                    continue

                t_listen = rule.get("listen", 60)
                t_anim = rule.get("anim", 15)
                t_books = rule.get("books", 2)

                for zh_name, day_records in all_days_students_map.items():
                    en_name = c_map.get(zh_name, "")
                    display_name = f"{zh_name}{en_name}"
                    
                    daily_emojis = []
                    full_days = 0

                    for i in range(days_count):
                        day_dt = s_date + timedelta(days=i)
                        day_str = day_dt.strftime("%Y-%m-%d")
                        
                        rec = day_records.get(day_str)
                        if rec:
                            l_time = rec.get("listen", 0)
                            a_time = rec.get("anim", 0)
                            b_cnt = rec.get("books", 0)
                            
                            is_listen = l_time >= t_listen
                            is_anim = a_time >= t_anim
                            is_books = b_cnt >= t_books
                            
                            if is_listen and is_anim and is_books:
                                daily_emojis.append(e_full)
                                full_days += 1
                            elif (l_time > 0 or a_time > 0 or b_cnt > 0):
                                daily_emojis.append(e_part)
                            else:
                                daily_emojis.append(e_zero)
                        else:
                            daily_emojis.append(e_zero)

                    emoji_str = " ".join(daily_emojis)
                    if full_days == days_count and days_count > 0 and e_badge:
                        emoji_str += f" {e_badge}"

                    matrix_lines.append(f"{emoji_str}  {display_name}")

                matrix_text = "\n".join(matrix_lines)
                reports[c_name] = template_str.format(
                    date_title=date_title,
                    matrix=matrix_text,
                    stats="{stats}"
                )

            else:
                # 传统分组模式：如果是单天直接请求该天，如果是多天则累加
                days_count = max(1, (e_date - s_date).days + 1)
                date_title = f"{s_date.month}月{s_date.day}日" if s_date == e_date else f"{s_date.month}.{s_date.day}-{e_date.month}.{e_date.day}"

                student_aggregated = {}

                for i in range(days_count):
                    day_dt = s_date + timedelta(days=i)
                    day_str = day_dt.strftime("%Y-%m-%d")
                    
                    detail_url = f"https://v2.ireadabc.com/api/reports/class/{c_id}/detail/{day_str}"
                    det_resp = requests.get(detail_url, headers=headers, timeout=8)
                    if det_resp.status_code == 200:
                        det_json = det_resp.json()
                        st_list = det_json.get("data", [])
                        if not st_list and isinstance(det_json, list):
                            st_list = det_json
                        if isinstance(st_list, dict):
                            st_list = st_list.get("students", []) or st_list.get("list", [])
                        
                        for st in st_list:
                            s_name = st.get("studentName") or st.get("name", "")
                            if not s_name:
                                continue
                            if s_name not in student_aggregated:
                                student_aggregated[s_name] = {"listen": 0, "anim": 0, "books": 0}
                            
                            student_aggregated[s_name]["listen"] += (st.get("listenTime") or st.get("listen_time", 0))
                            student_aggregated[s_name]["anim"] += (st.get("animTime") or st.get("anim_time", 0))
                            student_aggregated[s_name]["books"] += (st.get("booksCount") or st.get("books_count", 0))

                if not student_aggregated:
                    continue

                t_listen = rule.get("listen", 60) * days_count
                t_anim = rule.get("anim", 15) * days_count
                t_books = rule.get("books", 2) * days_count

                both, listen_only, anim_only, books, none = [], [], [], [], []

                for zh_name, totals in student_aggregated.items():
                    en_name = c_map.get(zh_name, "")
                    display_name = f"{zh_name}({en_name})" if en_name else zh_name

                    l_time = totals["listen"]
                    a_time = totals["anim"]
                    b_cnt = totals["books"]

                    is_listen = l_time >= t_listen
                    is_anim = a_time >= t_anim
                    is_books = b_cnt >= t_books

                    if is_listen and is_anim:
                        both.append(display_name)
                    elif is_listen:
                        listen_only.append(display_name)
                    elif is_anim:
                        anim_only.append(display_name)
                    else:
                        none.append(display_name)

                    if is_books:
                        books.append(display_name)

                reports[c_name] = template_str.format(
                    class_name=c_name,
                    report_type=report_type,
                    date_title=date_title,
                    target_listen=rule.get("listen", 60),
                    target_anim=rule.get("anim", 15),
                    target_books=rule.get("books", 2),
                    both_count=len(both),
                    both_list="、".join(both) if both else "无",
                    listen_only_count=len(listen_only),
                    listen_only_list="、".join(listen_only) if listen_only else "无",
                    anim_only_count=len(anim_only),
                    anim_only_list="、".join(anim_only) if anim_only else "无",
                    books_count=len(books),
                    books_list="、".join(books) if books else "无",
                    none_count=len(none),
                    none_list="、".join(none) if none else "无"
                )

        if not reports:
            return None, "未能成功解析到任何班级的打卡统计数据，请确认左侧是否添加并勾选了对应班级名称"

        return reports, None

    except Exception as e:
        return None, f"数据处理发生异常：{str(e)}"
