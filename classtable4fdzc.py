import requests, random, re
from bs4 import BeautifulSoup

from data import Course, School # Speacial thanks to junyilou/python-ical-timetable

def login(username, password, year="2023", term="上"):
    user = requests.session()

    login_id = user.get("https://jwc.fdzcxy.edu.cn/default.asp") # 获取 Cookie

    login_id = BeautifulSoup(login_id.text, 'lxml') # 解析登陆跳转页面 id
    login_id = login_id.select_one("#frm").attrs["action"]
    login_id = "." + login_id.split(".")[-1]

    captcha = user.get("https://jwc.fdzcxy.edu.cn/ValidateCookie.asp", stream=True) # 获取验证码
    with open("captcha.jpg", "wb") as captcha_img:
        captcha_img.write(captcha.content)

    captcha = input("Please input captcha: ")
    id = random.random()
    check_captcha = user.get("https://jwc.fdzcxy.edu.cn/ajax/chkCode.asp?code="+captcha+"&id="+str(id)) # 检查验证码

    while check_captcha.text != "ok": # 没的 do-while 我也只能这么写了（）
        captcha = input("Captcha is wrong, try again: ")
        id = random.random()
        check_captcha = user.get("https://jwc.fdzcxy.edu.cn/ajax/chkCode.asp?code="+captcha+"&id="+str(id))

    #login_redirect = user.post("https://jwc.fdzcxy.edu.cn/loginchk.asp?id="+login_id, allow_redirects=False,  # 获取登陆重定义向 url
    #                           data={"muser":username, "passwd": password, "code": captcha})
    #login_redirect = login_redirect.headers["Location"]

    user.post("https://jwc.fdzcxy.edu.cn/loginchk.asp?id="+login_id,
                data={"muser":username, "passwd": password, "code": captcha}) # 进行登陆跳转以获取 coocies

    class_timetable = user.get("https://jwc.fdzcxy.edu.cn/kb/kb_xs.asp", data={"xn":year, "xq":term}) # 获取课表页面
    class_timetable.encoding = "utf-8"
    return class_timetable.text



def parse_class_timetable(raw_html):
    class_timetable = BeautifulSoup(raw_html, 'lxml')
    class_info = []

    # 先读一波左边的数据

    for current_class_info_raw in class_timetable.select_one("body > table:nth-child(3)").select_one("td").select("tr"): # 选左侧课程情况表
        current_class_info_raw = current_class_info_raw.select("td") # 选中课程并过滤非课程项
        if len(current_class_info_raw)>2 and ("课程名称" not in current_class_info_raw[0].text):
            current_class_info = {
                "name": current_class_info_raw[0].text.strip().split(' ')[0], # 班级是写在课程里的，用空格分开
                "teacher": current_class_info_raw[2].text.strip(),
                "duration": current_class_info_raw[10].text.strip().split('～')
            }
            class_info.append(current_class_info)

    #print(class_info)
    # 开始填课表

    all_classes= []

    for current_day in list(range(1,8)): # 一周 7 天
        for current_num in list(range(1,10)): # 一天 9 节课
            current_class_raw = class_timetable.find("td", id=current_num*10+current_day, align="center") # 这个 id 就是这个规律，一格一格方格找

            if current_class_raw and len(current_class_raw) > 7: # 世界无常，佛祖保佑我用这么丑的解析！单双周也是全推在一起的....
                current_class_1st = {
                    "name" : None, # 课程名称
                    "teacher" : None, # 老师
                    "location" : None, # 地点
                    "index" : [current_num, current_num+int(current_class_raw.attrs["rowspan"])-1], # 节数
                    "dayofweek" : current_day, # 每周几
                    "duration" : [0,0,0, True], # 上课周（第一位代表单双周、第二三位是周数、
                                                # 第四位确认是否特殊情况（实际周数与左侧课表不符合））
                }
                current_class_2nd = {
                    "name" : None, # 课程名称
                    "teacher" : None, # 老师
                    "location" : None, # 地点
                    "index" : [current_num, current_num+int(current_class_raw.attrs["rowspan"])-1], # 节数
                    "dayofweek" : current_day, # 每周几
                    "duration" : [0,0,0, True], # 上课周
                }

                for raws in current_class_raw: # 依次读源数据
                    if "[" in raws:
                        raws = re.findall('\[(.*?)\]', raws) # 单双周和地点
                        if current_class_1st["location"] == None: # 因为不知道单双周哪个在先所以判断一下
                            current_class_1st["duration"][0] = raws[0]
                            current_class_1st["location"] = raws[1]
                        else:
                            current_class_2nd["duration"][0] = raws[0]
                            current_class_2nd["location"] = raws[1]
                    elif "周" in raws: # 填课程周数
                        if current_class_1st["duration"][3]:
                            current_class_1st["duration"][1] = int(re.findall('\((.*?)\-', raws)[0])
                            current_class_1st["duration"][2] = int(re.findall('\-(.*?)周', raws)[0])
                            current_class_1st["duration"][3] = False # 确认这里改过了
                        else:
                            current_class_2nd["duration"][1] = int(re.findall('\((.*?)\-', raws)[0])
                            current_class_2nd["duration"][2] = int(re.findall('\-(.*?)周', raws)[0])
                            current_class_2nd["duration"][3] = False
                    elif "班" in raws:
                        for current_class_info in class_info: # 又是遍历嗯搜....
                            if current_class_info["name"] in raws:
                                if current_class_1st["name"] == None:
                                    current_class_1st["name"] = current_class_info["name"] # 替换一下课程名
                                    current_class_1st["teacher"] = current_class_info["teacher"] # 填一下老师
                                    current_class_1st["duration"][1] = int(current_class_info["duration"][0]) # 课程名称最先出现
                                    current_class_1st["duration"][2] = int(current_class_info["duration"][1]) # 这里就先填了左侧的，如果后面有就会被覆盖掉
                                else:
                                    current_class_2nd["name"] = current_class_info["name"]
                                    current_class_2nd["teacher"] = current_class_info["teacher"]
                                    current_class_2nd["duration"][1] = int(current_class_info["duration"][0])
                                    current_class_2nd["duration"][2] = int(current_class_info["duration"][1])
                                
                all_classes.append(current_class_1st)
                all_classes.append(current_class_2nd)

            elif current_class_raw: # 因为是遍历，可能有的方格没课，所以要判断一下

                current_class = { # 用个字典存，到时候填到生成器里
                    "name" : None, # 课程名称
                    "teacher" : None, # 老师
                    "location" : None, # 地点
                    "index" : [current_num, current_num+int(current_class_raw.attrs["rowspan"])-1], # 节数
                    "dayofweek" : current_day, # 每周几
                    "duration" : None, # 上课周
                }

                for raws in current_class_raw: # 依次读源数据
                    if "[" in raws: # 填课程位置
                        raws = re.findall('\[(.*?)\]', raws)
                        current_class["location"] = raws[0]
                    elif "周" in raws: # 填课程周数
                        current_class["duration"] = [int(re.findall('\((.*?)\-', raws)[0]), int(re.findall('\-(.*?)周', raws)[0])]
                    elif "班" in raws: # 填课程名称等等，因为课程名可以对应左侧课程情况表，所有顺便填一下老师和周数
                        for current_class_info in class_info: # 又是遍历嗯搜....
                            if current_class_info["name"] in raws:
                                current_class["name"] = current_class_info["name"]
                                current_class["teacher"] = current_class_info["teacher"]
                                current_class["duration"] = [int(i) for i in current_class_info["duration"]]

                all_classes.append(current_class)

    return all_classes

if __name__ == "__main__":
    username = input("Please input username: ")
    password = input("Please input password: ")
    courses = []
    
    for current_class in parse_class_timetable(login(username, password)):
        if len(current_class["duration"]) == 2:
            courses.append(Course(current_class["name"], current_class["teacher"], current_class["location"], None, 
                                  current_class["dayofweek"], Course.week(current_class["duration"][0], current_class["duration"][1]), 
                                  current_class["index"]))
        elif len(current_class["duration"]) == 2 and current_class["duration"][0] == current_class["duration"][1]:
            courses.append(Course(current_class["name"], current_class["teacher"], current_class["location"], None, 
                                  current_class["dayofweek"], current_class["duration"][0], 
                                  current_class["index"]))
        elif current_class["duration"][0] == "单":
            courses.append(Course(current_class["name"], current_class["teacher"], current_class["location"], None, 
                                  current_class["dayofweek"], Course.odd_week(current_class["duration"][1], current_class["duration"][2]), 
                                  current_class["index"]))
        elif  current_class["duration"][0] == "双":
            courses.append(Course(current_class["name"], current_class["teacher"], current_class["location"], None, 
                                  current_class["dayofweek"], Course.even_week(current_class["duration"][1], current_class["duration"][2]), 
                                  current_class["index"]))
    
    school = School(
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
        (19, 55)
    ],
    start=(2023, 8, 28), # 2023 年 8 月 28 日是开学第一周星期一
    courses=courses
    )
    
    with open("课表.ics", "w") as w:
        w.write(school.generate())
