import re
import requests
import traceback
import math
import unicodedata
from datetime import date, timedelta

AUTH_EXPIRED_MESSAGE = "登录已过期，请重新登录。"

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

DEFAULT_RULE = {"listen": 60, "anim": 15, "books": 2}


def clean_num(value):
    """Read a number without truncating decimals or treating malformed data as zero."""
    if value is None or value == "":
        return 0.0
    text = str(value).strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?(?:本|次)?", text):
        raise ValueError(f"无法识别的数据数值：{text}")
    number = float(re.match(r"\d+(?:\.\d+)?", text)[0])
    if not math.isfinite(number):
        raise ValueError("数据数值不可用")
    return number


def duration_minutes(value):
    text = str(value).strip() if value is not None else ""
    if not text or re.fullmatch(r"\d+(?:\.\d+)?", text):
        return clean_num(value)
    pattern = r"(\d+(?:\.\d+)?)\s*(小时|分钟|分|秒|h|min|s)"
    parts = re.findall(pattern, text)
    if not parts or re.sub(pattern, "", text).strip():
        raise ValueError(f"无法识别时长单位：{text}")
    factors = {"小时": 60, "h": 60, "分钟": 1, "分": 1, "min": 1, "秒": 1 / 60, "s": 1 / 60}
    return sum(clean_num(number) * factors[unit] for number, unit in parts)


def student_metrics(student):
    values = []
    raw = []
    for keys, parser in (
        (("listen", "audio_time", "listenTime"), duration_minutes),
        (("animation", "anim", "animTime"), duration_minutes),
        (("grading", "booksCount"), clean_num),
    ):
        key = next((key for key in keys if key in student), None)
        if key is None:
            raise ValueError(f"接口缺少 {keys[0]} 字段，已停止生成，避免误判")
        raw.append(student[key])
        values.append(parser(student[key]))
    # The platform's read field is extracurricular reading, not grading homework.
    if values[2] != int(values[2]):
        raise ValueError("分级作业数量不是整数，已停止生成")
    return values, raw


def class_config(class_name, rules, mappings, default_rule):
    def normalized(name):
        text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", name)).casefold()
        return text[:-1] if text.endswith("班") else text

    key = class_name if class_name in rules else None
    if key is None:
        matches = [name for name in rules if normalized(name) == normalized(class_name)]
        if len(matches) > 1:
            raise ValueError(f"班级“{class_name}”匹配到多条配置，请统一班级名称")
        key = matches[0] if matches else None
    rule = rules[key] if key is not None else default_rule
    if not isinstance(rule, dict) or any(k not in rule for k in DEFAULT_RULE):
        raise ValueError(f"班级“{class_name}”的目标配置不完整")
    for k in DEFAULT_RULE:
        if isinstance(rule[k], bool) or not isinstance(rule[k], (int, float)) or not math.isfinite(rule[k]) or rule[k] < 0:
            raise ValueError(f"班级“{class_name}”的目标配置无效")
    source = f"班级配置：{key}" if key is not None else "默认规则（未匹配到班级配置）"
    mapping = mappings.get(class_name, mappings.get(key, ""))
    return rule, parse_name_map(mapping), source


def fetch_statistics(token, class_id, start, end):
    response = requests.get(
        f"https://v2.ireadabc.com/api/v3/reports/statistics/class/{class_id}",
        headers={"Token": token, "Client-Type": "BROWSER", "User-Agent": "Mozilla/5.0"},
        params={"start": start, "end": end}, timeout=15,
    )
    if response.status_code in (401, 403):
        raise ValueError(AUTH_EXPIRED_MESSAGE)
    if response.status_code != 200:
        raise ValueError(f"班级 {class_id} 在 {start} 至 {end} 的数据请求失败（{response.status_code}），已停止生成")
    payload = response.json()
    if isinstance(payload, dict) and payload.get("code") in (401, 403, "401", "403"):
        raise ValueError(AUTH_EXPIRED_MESSAGE)
    if isinstance(payload, dict) and payload.get("code") not in (None, 0, 200, "0", "200"):
        raise ValueError("平台返回数据错误，已停止生成")
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    if isinstance(rows, dict):
        rows = next((rows[k] for k in ("students", "rows", "list") if k in rows), None)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("平台数据格式无法识别，已停止生成")
    return rows


def format_student_name(raw_name, eng_name, english_only=False):
    if not raw_name:
        return ""
    raw_name = str(raw_name).strip()
    if english_only:
        for candidate in (eng_name, raw_name):
            parts = re.findall(r"[A-Za-z]+(?:[ '’-][A-Za-z]+)*", unicodedata.normalize("NFKC", str(candidate or "")))
            if parts:
                return " ".join(parts)
        return raw_name
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

def fetch_data_via_api(auth_token, report_type, start_date, end_date, class_rules_config, name_maps_config, default_rule, template_str, mode="traditional", emoji_config=None, diagnostics=None, english_only=False):
    if emoji_config is None:
        emoji_config = {"full": "🍓", "part": "✅", "zero": "🚫", "badge": "✔️"}
    if diagnostics is not None:
        diagnostics.clear()
    if end_date < start_date:
        return None, "结束日期不能早于开始日期"
    token = auth_token.strip()
    try:
        response = requests.get(
            "https://v2.ireadabc.com/api/teacher/classes/page/all",
            headers={"Token": token, "Client-Type": "BROWSER", "User-Agent": "Mozilla/5.0"}, timeout=15,
        )
        if response.status_code in (401, 403):
            return None, AUTH_EXPIRED_MESSAGE
        if response.status_code != 200:
            return None, f"请求班级列表失败 (状态码: {response.status_code})"
        payload = response.json()
        if isinstance(payload, dict) and payload.get("code") in (401, 403, "401", "403"):
            return None, AUTH_EXPIRED_MESSAGE
        classes = payload.get("data", payload) if isinstance(payload, dict) else payload
        if isinstance(classes, dict):
            classes = next((classes[k] for k in ("rows", "list", "classes") if k in classes), [])
        if not isinstance(classes, list) or not classes:
            return None, "未能获取到班级列表，请确认登录及接口数据"

        days = (end_date - start_date).days + 1
        dates = [(start_date + timedelta(days=i)).isoformat() for i in range(days)]
        reports = {}
        for item in classes:
            class_id = str(item.get("id") or item.get("class_id") or item.get("classId") or "")
            class_name = item.get("class_name") or item.get("name") or item.get("className") or f"班级_{class_id}"
            if not class_id:
                raise ValueError("接口缺少班级编号，已停止生成")
            rule, mapping, source = class_config(class_name, class_rules_config, name_maps_config, default_rule)
            students = {}
            glory, effort, zero = [], [], []
            ranges = [(day, day) for day in dates] if mode == "matrix" else [(dates[0], dates[-1])]
            for day_index, (first, last) in enumerate(ranges):
                rows = fetch_statistics(token, class_id, first, last)
                seen = set()
                for student in rows:
                    raw_name = student.get("name") or student.get("student_name") or student.get("studentName")
                    if not isinstance(raw_name, str) or not raw_name.strip():
                        raise ValueError("学生数据缺少姓名，已停止生成")
                    raw_name = raw_name.strip()
                    student_id = str(student.get("id") or student.get("student_id") or student.get("studentId") or raw_name)
                    if student_id in seen:
                        raise ValueError(f"班级“{class_name}”有重复学生记录，已停止生成")
                    seen.add(student_id)
                    chinese_name = re.sub(r"[a-zA-Z\s]", "", raw_name)
                    display_name = format_student_name(raw_name, mapping.get(chinese_name, mapping.get(raw_name, "")), english_only=english_only)
                    amounts, raw = student_metrics(student)
                    multiplier = 1 if mode == "matrix" else days
                    targets = [rule[key] * multiplier for key in ("listen", "anim", "books")]
                    missing = [f"{label}还缺{target - amount:g}{unit}" for label, unit, amount, target in zip(
                        ("听音", "动画", "分级绘本"), ("分钟", "分钟", "本"), amounts, targets,
                    ) if amount < target]
                    status = "full" if not missing else "zero" if not any(amounts) else "part"
                    if diagnostics is not None:
                        diagnostics.append({
                            "班级": class_name, "日期": first if first == last else f"{first}至{last}",
                            "学生": display_name, "规则来源": source,
                            "听音原始": str(raw[0]), "听音分钟": amounts[0], "听音目标": targets[0],
                            "动画原始": str(raw[1]), "动画分钟": amounts[1], "动画目标": targets[1],
                            "分级原始": str(raw[2]), "分级本数": amounts[2], "分级目标": targets[2],
                            "判断": {"full": "全部达标", "part": "部分完成", "zero": "未打卡"}[status],
                            "未达标原因": "；".join(missing),
                        })
                    if mode == "matrix":
                        record = students.setdefault(student_id, {"name": display_name, "statuses": ["zero"] * days})
                        record["statuses"][day_index] = status
                    elif status == "full":
                        glory.append(f"{display_name} (听音{amounts[0]:g}min, 动画{amounts[1]:g}min, 绘本{amounts[2]:g}本)")
                    elif status == "zero":
                        zero.append(display_name)
                    else:
                        effort.append(f"{display_name}：部分完成（{'，'.join(missing)}）")

            if mode == "matrix":
                lines = []
                full_count = zero_count = 0
                for record in students.values():
                    statuses = record["statuses"]
                    full = all(status == "full" for status in statuses)
                    full_count += full
                    zero_count += all(status == "zero" for status in statuses)
                    line = f"{''.join(emoji_config[status] for status in statuses)}  {record['name']}"
                    if full and emoji_config.get("badge"):
                        line += f" {emoji_config['badge']}"
                    lines.append(line)
                total = len(students)
                attendance_rate = round(full_count / total * 100, 1) if total else 0.0
                stats = f"📊 学情统计汇总：\n🏆 全勤达标：{full_count} 人 ({attendance_rate}%)\n💪 持续加油：{total - full_count - zero_count} 人\n⚠️ 未打卡提醒：{zero_count} 人"
                template = template_str if "{stats}" in template_str else template_str + "\n\n--------------------\n{stats}"
                content = template.format(
                    class_name=class_name, date_title=f"{start_date.month}.{start_date.day}--{end_date.month}.{end_date.day}",
                    matrix="\n".join(lines) if lines else "（暂无打卡数据）", total_students=total,
                    full_attendance_count=full_count, attendance_rate=attendance_rate, stats=stats,
                )
                reports[class_name] = content
            else:
                template = template_str if "{glory_list}" in template_str else DEFAULT_TEMPLATE
                content = template.format(
                    class_name=class_name, date_title=start_date.strftime("%m月%d日") if days == 1 else f"{dates[0]}至{dates[-1]}",
                    glory_list="\n".join(glory) if glory else "无", effort_list="\n".join(effort) if effort else "无",
                    zero_list="\n".join(zero) if zero else "无",
                )
                reports[class_name] = content
        return reports, None
    except Exception as error:
        traceback.print_exc()
        return None, str(error)
