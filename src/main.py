#!/usr/bin/env python3
import argparse
import httpx
import random
import re
from bs4 import BeautifulSoup

import icaltimetable
import captcha_recognizer

def split_list(tlist, n):
    """
    将列表每 n 个元素分成一组
    """
    return [tlist[i : i + n] for i in range(0, len(tlist), n)]


def unnest_list(nlist):
    """
    展平嵌套列表，例如：[[2], [3], [4]] -> [2, 3, 4]
    """
    return [item for sublist in nlist for item in sublist]


def indices_list(lst, condition):
    """
    返回满足条件的列表元素的索引
    """
    return [i for i, elem in enumerate(lst) if condition(elem)]


def indices_split_list(lst, indices):
    """
    根据给定索引，将列表拆分为多个子列表
    """
    return [lst[i:j] for i, j in zip(indices, indices[1:] + [None])]


def get_raw_classtable_page(username, password, school_year, semester, base_url):
    """
    使用提供的凭证从网页获取原始课表页面
    该函数会下载验证码图片，并提示用户输入验证码
    """
    recognizer = captcha_recognizer.BMPTextRecognizer()
    with httpx.Client(default_encoding="utf-8", timeout=10.0) as client:
        index_page = client.get(base_url + "default.asp").text
        # 从主页中获取登录表单的链接
        login_form = BeautifulSoup(index_page, "lxml").select_one("#frm")
        login_url = base_url + login_form.attrs["action"]

        # 获取并保存验证码图片
        captcha_image = client.get(base_url + "ValidateCookie.asp").content
        with open("captcha.bmp", "wb") as f:
            f.write(captcha_image)

        # 循环直到用户输入正确的验证码
        captcha_code = recognizer.process_bmp("./captcha.bmp")
        captcha_id = str(random.random())
        captcha_check = client.get(
            base_url + f"ajax/chkCode.asp?code={captcha_code}&id={captcha_id}"
        ).text
        if captcha_check != "ok":
            print("验证码错误，请重试。")
            exit()

        # 提交登录表单数据
        client.post(
            login_url,
            data={"muser": username, "passwd": password, "code": captcha_code},
        )

        # 登录后获取原始课表页面
        raw_classtable_page = client.post(
            base_url + "kb/kb_xs.asp",
            data={
                "xn": school_year,
                "xq": semester,
            },
        ).text

    return raw_classtable_page


def parse_raw_page(raw_page):
    """
    将原始课表 HTML 页面解析成一系列课程对象，使用 icaltimetable 生成
    """
    page_bs = BeautifulSoup(raw_page, "lxml")

    # 提取页面左侧表格课程内容
    page_left_table = (
        page_bs.select_one("body > table:nth-child(3)")
        .select_one("td")
        .select("tr:not([height])")
    )
    page_left_table = [each.find_all("td") for each in page_left_table]

    # 格式化课程内容
    page_left_table = {
        each[0].text[1:].replace(" ", ""): {  # 以课程的完整名称作为键
            "name": each[0].text[1:].replace(" ", "").split("(")[0],
            "teacher": each[2].text.replace(" ", ""),
            "weeks": split_list(split_list(each[10].text.replace("～", ""), 2), 2),
        }
        for each in page_left_table
    }

    page_right_table = [
        {
            "info": [
                info
                # 表格中每一格的内容
                for info in [info for info in each.contents if str(info) != "<br/>"]
            ],
            "weekday": int(each.attrs["id"]) % 10,  # 星期x
            "index": int(each.attrs["id"]) // 10,  # 第x节
            "duration": int(each.attrs["rowspan"]),  # 上x节
        }
        for each in page_bs.find_all("td", align="center")
        if "id" in each.attrs and "rowspan" in each.attrs
    ]

    page_right_table = [
        dict(
            each,
            info=unnest_list(
                [
                    # 地点
                    re.findall(r"\[(.*?)\]", each)
                    if "[" in each
                    # 周数（可能存在多个周，两两拆分）
                    else split_list(
                        split_list(
                            split_list(
                                re.findall(
                                    r"\((.*?)\)",
                                    each.replace("周", "")
                                    .replace("-", "")
                                    .replace(",", ""),
                                )[0],
                                2,
                            ),
                            2,
                        ),
                        2,
                    )
                    if "周" in each
                    # 课程
                    else [each]
                    for each in each["info"]
                ]
            ),
        )
        for each in page_right_table
    ]

    # 根据课程拆分列表为子列表（一个单元格中可能存在多个课程）
    page_right_table = [
        dict(
            each,
            info=indices_split_list(
                each["info"],
                indices_list(
                    each["info"], lambda e: e in tuple(page_left_table.keys())
                ),
            ),
        )
        for each in page_right_table
    ]

    # 现在每个元素都代表一堂课，填充课程信息
    courses = [
        {
            "weekday": eaches["weekday"],
            "index": eaches["index"],
            "duration": eaches["duration"],
            "name": next(
                filter(lambda e: e in tuple(page_left_table.keys()), each), None
            ),
            "weeks": next(filter(lambda e: isinstance(e, list), each), None),
            "classroom": next(
                filter(
                    lambda e: (
                        e not in tuple(page_left_table.keys())
                        and not isinstance(e, list)
                        and not e.startswith("单")
                        and not e.startswith("双")
                    ),
                    each,
                ),
                None,
            ),
            "even": any(
                filter(lambda e: isinstance(e, str) and e.startswith("双"), each)
            ),
            "odd": any(
                filter(lambda e: isinstance(e, str) and e.startswith("单"), each)
            ),
        }
        for eaches in page_right_table
        for each in eaches["info"]  # 一个单元格中可能包含几节课
    ]

    # 从左侧课程信息中继续填充
    courses = [
        dict(
            course,
            weeks=page_left_table[course["name"]]["weeks"],
            teacher=page_left_table[course["name"]]["teacher"],
        )
        if not course["weeks"]
        else dict(course, teacher=page_left_table[course["name"]]["teacher"])
        for course in courses
    ]

    # 继续拆分课程，这次是将周数拆出来
    courses = [
        dict(course, weeks=[int(i) for i in week])
        for course in courses
        for week in course["weeks"]
    ]

    # 然后生成具体上课周
    courses = [
        dict(
            course,
            weeks=icaltimetable.Course.odd_week(course["weeks"][0], course["weeks"][1]),
        )
        if course["odd"]
        else dict(
            course,
            weeks=icaltimetable.Course.even_week(
                course["weeks"][0], course["weeks"][1]
            ),
        )
        if course["even"]
        else dict(course, weeks=[course["weeks"][0]])
        if course["weeks"][0] == course["weeks"][1]
        else dict(
            course,
            weeks=icaltimetable.Course.week(course["weeks"][0], course["weeks"][1]),
        )
        for course in courses
    ]

    # 最后生成课表
    courses = [
        icaltimetable.Course(
            name=course["name"],
            teacher=course["teacher"],
            classroom=course["classroom"],
            weekday=course["weekday"],
            weeks=course["weeks"],
            indexes=[course["index"], course["index"] + course["duration"] - 1],
            location=None,
        )
        for course in courses
    ]

    return courses


def build_school(courses):
    """
    使用 icaltimetable 构造 School 对象，内部课表信息为硬编码数据
    """
    school = icaltimetable.School(
        duration=45,  # 每节课 45 分钟
        timetable=[
            (8, 00),  # 上午第一节课
            (8, 55),
            (10, 00),
            (10, 55),
            (14, 00),  # 下午第一节课
            (14, 55),
            (16, 00),
            (16, 55),
            (19, 00),  # 晚自习
            (19, 55),
            (20, 50),
        ],
        start=(2025, 2, 24),  # 开始日期：2025年2月24日（星期一）
        courses=courses,
    )
    return school


def parse_args():
    """
    解析并返回命令行参数
    """
    parser = argparse.ArgumentParser(description="生成课表 ICS 文件")
    parser.add_argument(
        "--username", type=str, default="", help="登录用户名（web 模式下必填）"
    )
    parser.add_argument(
        "--password", type=str, default="", help="登录密码（web 模式下必填）"
    )
    parser.add_argument(
        "--school-year", type=str, default="2024", help="学年 (例如: 2024)"
    )
    parser.add_argument(
        "--semester", type=str, default="下", help="学期 (例如: '上' 或 '下')"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="https://jwc.fdzcxy.edu.cn/",
        help="课表系统的基础 URL",
    )
    parser.add_argument(
        "--source",
        choices=["web", "file"],
        default="web",
        help="数据来源：网络或本地文件",
    )
    parser.add_argument(
        "--input-file", type=str, default="", help="若使用文件来源，则提供输入文件路径"
    )
    parser.add_argument(
        "--output-file", type=str, default="课表.ics", help="输出的 ICS 文件名"
    )
    args = parser.parse_args()

    # 参数校验：如果选择 web 模式，则用户名和密码不能为空
    if args.source == "web":
        if not args.username or not args.password:
            parser.error("使用 web 数据源时，必须提供 --username 和 --password 参数。")
    # 参数校验：如果选择 file 模式，则必须提供输入文件路径
    if args.source == "file" and not args.input_file:
        parser.error("使用 file 数据源时，必须提供 --input-file 参数。")
    return args


def main():
    args = parse_args()

    if args.source == "web":
        print("正在从网络获取课表数据...")
        raw_page = get_raw_classtable_page(
            args.username, args.password, args.school_year, args.semester, args.base_url
        )
    elif args.source == "file":
        print(f"正在从文件加载课表数据：{args.input_file}")
        with open(args.input_file, "r", encoding="utf-8") as f:
            raw_page = f.read()
    else:
        raise ValueError("未知的数据来源选项。")

    # 解析原始 HTML 页面，生成课程列表
    courses = parse_raw_page(raw_page)
    school = build_school(courses)

    # 生成 ICS 内容，并保存到输出文件
    ics_content = school.generate()
    with open(args.output_file, "w", encoding="utf-8") as w:
        w.write(ics_content)
    print(f"ICS 文件已生成并保存为 '{args.output_file}'。")


if __name__ == "__main__":
    main()
