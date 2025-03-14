# fdzc-ical-generator
Fuzhou University Zhicheng College ICS Schedule Generator 福州大学至诚学院 ics 课表生成

## Usage

This script generates an ICS file containing a class schedule. It supports fetching data from a web source or a local file.

### Command-line Arguments

```shell
usage: main.py [--username USERNAME] [--password PASSWORD]
                 [--school-year SCHOOL_YEAR] [--semester SEMESTER]
                 [--base-url BASE_URL] [--source {web,file}]
                 [--input-file INPUT_FILE] [--output-file OUTPUT_FILE]
```

### Arguments:

- `--username`: (Required for web mode) Username for login.
- `--password`: (Required for web mode) Password for login.
- `--school-year`: Academic year (default: `2024`).
- `--semester`: Semester, either `'上'` (first) or `'下'` (second) (default: `'下'`).
- `--base-url`: Base URL of the schedule system (default: `https://jwc.fdzcxy.edu.cn/`).
- `--source`: Data source, either `web` or `file` (default: `web`).
- `--input-file`: If using file source, provide the input file path.
- `--output-file`: Name of the generated ICS file (default: `课表.ics`).

### Examples:

#### Fetch schedule from the web:
```shell
python main.py --username myuser --password mypass --school-year 2024 --semester 上
```

#### Use a local file as data source:
```shell
python main.py --source file --input-file my_schedule.html --output-file my_schedule.ics
```

### Notes:
- If using `web` mode, both `--username` and `--password` must be provided.
- If using `file` mode, `--input-file` must be specified.
- The generated ICS file can be imported into calendar applications.

## Acknowledgement
1. [junyilou/python-ical-timetable](https://github.com/junyilou/python-ical-timetable)
