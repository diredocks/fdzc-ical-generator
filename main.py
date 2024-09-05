import httpx
import random
import re
from bs4 import BeautifulSoup

import icaltimetable

def get_raw_classtable_page():
    username = ""
    password = ""
    school_year = "2024"
    semester = "上"
    base_url = "https://jwc.fdzcxy.edu.cn/"
    
    with httpx.Client(default_encoding="utf-8") as client:
        index_page = client.get(base_url+"default.asp").text

        login_url = BeautifulSoup(index_page, 'lxml')
        login_url = base_url+login_url.select_one("#frm").attrs["action"] # 获取登陆链接

        captcha_image = client.get(base_url+"ValidateCookie.asp").content # 获取验证码图片
        with open("captcha.jpg", "wb") as f:
            f.write(captcha_image)

        while True:
            captcha_code = input("captcha: ")
            captcha_id = str(random.random())
            captcha_check = client.get(
                base_url+f"ajax/chkCode.asp?code={captcha_code}&id={captcha_id}"
            ).text # 检查验证码
            if captcha_check == "ok":
                break
            else:
                print("wrong captcha")

        client.post(login_url, 
            data={
                "muser": username,
                "passwd": password,
                "code": captcha_code
        })

        raw_classtable_page = client.post(
            base_url+"kb/kb_xs.asp",
            data={
                "xn": school_year,
                "xq": semester,
            }
        ).text

    return raw_classtable_page

def split_list(tlist, n):
    '''
    每 n 个元素分一组
    '''
    return [
        tlist[i:i+n] 
        for i in range(0, len(tlist), n)
    ]

def unnest_list(nlist):
    '''
    [[2], [3], [4]] -> [2, 3, 4]
    '''
    return [
        nested
        for nesteds in nlist
        for nested in nesteds
   ]

def indices_list(list, condition):
    return [
        i
        for i, elem in enumerate(list)
        if condition(elem)
    ]

def indices_split_list(list, indices):
    return [
        list[i:j]
        for i, j in zip(indices, indices[1:]+[None])
    ]

def parse_raw_page(raw_page):
    page_bs = BeautifulSoup(raw_page, "lxml")

    # 提取页面左侧表格课程内容
    page_left_table = page_bs.select_one("body > table:nth-child(3)").select_one("td").select("tr:not([height])")
    page_left_table = [
        each.findChildren("td")
        for each in page_left_table
    ]

    # 格式化课程内容
    page_left_table = {
        each[0].text[1:].replace(" ", ""): { # 以课程的完整名称作为键
            "name": each[0].text[1:].replace(" ", "").split("(")[0],
            "teacher": each[2].text.replace(" ", ""),
            "weeks": split_list(
                        split_list(
                            each[10].text.replace("～", "")
                        , 2)
                     , 2)
        }
        for each in page_left_table
    }

    page_right_table = [
        {
            "info": [
                info
                # 表格中每一格的内容
                for info in [
                    info for info in each.contents
                    if str(info) != "<br/>"
                ]
            ],
            "weekday": int(each.attrs["id"]) % 10, # 星期x
            "index": int(each.attrs["id"]) // 10,  # 第x节
            "duration": int(each.attrs["rowspan"]) # 上x节
        }
        for each in page_bs.find_all("td", align="center")
        if "id" in each.attrs and "rowspan" in each.attrs
    ]

    page_right_table = [
        dict(each, info=unnest_list([
            # 地点
            re.findall(r'\[(.*?)\]', each)
            if "[" in each
            # 周数（可能存在多个周，两两拆分）
            else
            split_list(
                split_list(
                    split_list(
                        re.findall(r'\((.*?)\)',
                            each.replace("周", "").replace("-", "").replace(",", "")
                        )[0],
                    2),
                2),
            2)
            if "周" in each
            # 课程
            else [each]
            for each in each["info"]
        ]))
        for each in page_right_table
    ]

    # 根据课程拆分列表为子列表（一个单元格中可能存在多个课程）
    page_right_table = [
        dict(
            each, info=
                indices_split_list(
                    each["info"],
                    indices_list(
                        each["info"],
                        lambda e: e in tuple(page_left_table.keys())
                    )
                )
        )
        for each in page_right_table
    ]

    # 现在每个元素都代表一堂课，填充课程信息
    courses = [
        {
            "weekday": eaches["weekday"],
            "index": eaches["index"],
            "duration": eaches["duration"],
            "name": next(filter(
                lambda e:
                    e in tuple(page_left_table.keys()),
                each), None),
            "weeks": next(filter(
                lambda e: 
                    isinstance(e, list),
                each), None),
            "classroom": next(filter(
                lambda e: (
                    e not in tuple(page_left_table.keys())
                    and not isinstance(e, list)
                    and not e.startswith("单")
                    and not e.startswith("双")
                ),
                each), None),
            "even": any(filter(
                lambda e:
                    isinstance(e, str) and
                    e.startswith("双"),
                each)),
            "odd": any(filter(
                lambda e: 
                    isinstance(e, str) and
                    e.startswith("单"),
                each)),
        }
        for eaches in page_right_table
        for each in eaches["info"] # 一个单元格中可能包含几节课
    ]

    # 从左侧课程信息中继续填充
    courses = [
        dict(
            course,
            weeks=page_left_table[course["name"]]["weeks"],
            teacher=page_left_table[course["name"]]["teacher"]
        )
        if not course["weeks"]
        else dict(
            course, teacher=page_left_table[course["name"]]["teacher"]
        )
        for course in courses
    ]

    # 继续拆分课程，这次是将周数拆出来
    courses = [
        dict(
            course,
            weeks=[int(i) for i in week]
        )
        for course in courses
        for week in course["weeks"]
    ]

    # 然后生成具体上课周
    courses = [
        dict(
            course,
            weeks=icaltimetable.Course.odd_week(course["weeks"][0],
                                                course["weeks"][1])
        )
        if course["odd"]
        else
        dict(
            course,
            weeks=icaltimetable.Course.even_week(course["weeks"][0],
                                                 course["weeks"][1])
        )
        if course["even"]
        else dict(
            course,
            weeks=course["weeks"][0]
        )
        if course["weeks"][0] == course["weeks"][1]
        else dict(
            course,
            weeks=icaltimetable.Course.week(course["weeks"][0],
                                      course["weeks"][1])
        )
        for course in courses
    ]

    print(courses)
    # 最后生成课表
    courses = [
        icaltimetable.Course(
            name = course["name"],
            teacher = course["teacher"],
            classroom = course["classroom"],
            weekday = course["weekday"],
            weeks = course["weeks"],
            indexes = [course["index"],
                       course["index"]+course["duration"]-1],
            location = None,
        )
        for course in courses
    ]

    return courses

if __name__ == "__main__":
    '''
    raw_classtable_page = get_raw_classtable_page()
    print(raw_classtable_page)
    with open('classtable3.html', 'w') as file:
        file.write(raw_classtable_page)
    '''

    with open("classtable.html", "r") as file:
        raw_page = file.read()
    courses = parse_raw_page(raw_page)

    school = icaltimetable.School(
        duration=45, # 每节课时间为 45 分钟
        timetable=[
            (8, 00), # 上午第一节课
            (8, 55),
            (10, 00),
            (10, 55),
            (14, 00), # 下午第一节课
            (14, 55),
            (16, 00),
            (16, 55),
            (19, 00),  # 晚自习
            (19, 55),
            (20, 50),
        ],
        start=(2024, 8, 26), # 2024 年 8 月 26 日是开学第一周星期一
        courses=courses
    )

    with open("课表.ics", "w") as w:
        w.write(school.generate())
