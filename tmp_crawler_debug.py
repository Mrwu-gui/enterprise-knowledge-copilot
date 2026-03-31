from backend.generic_crawler import _extract_html_lines, _apply_rules
from pathlib import Path


html = Path("/Users/shuaiqideguigegegegege/conproject/lok-bak/crawler_test_chinaunicom.html").read_text(encoding="utf-8")
title, lines = _extract_html_lines(html, 60)
print("TITLE:", title)
print("RAW_LINES_COUNT:", len(lines))
for i, line in enumerate(lines[:20], 1):
    print(f"RAW[{i}]:", line)

rule_text = """selector=.article h1,.article h2,.article p
include=中国联通|维护|公告|通知|处理要求|恢复确认
exclude=广告相关推荐
limit=20
"""

final_lines = _apply_rules(lines, html, rule_text)
print("FINAL_LINES_COUNT:", len(final_lines))
for i, line in enumerate(final_lines[:20], 1):
    print(f"FINAL[{i}]:", line)
