# 网络来源说明

记录哪些源文件存在问题，以及用于替换的网络来源。

## 需替换文件（docx 版本有条文缺失）

| 文件名 | 问题 | 替换来源 | 状态 |
|--------|------|----------|------|
| 最高人民法院关于适用《中华人民共和国刑事诉讼法》的解释_20210126.docx | 缺第81、271、300、372条 | https://www.court.gov.cn/zixun/xiangqing/286491.html | ✅ 已替换 |
| 最高人民法院关于执行担保若干问题的规定_20201229.docx | 缺第5条 | http://gongbao.court.gov.cn/Details/8052c6020c2d7cba30c99fc450d61e.html | ✅ 已替换 |

## 新增来源（无对应 docx）

| 文件名 | 来源 | 状态 |
|--------|------|------|
| 全国法院民商事审判工作会议纪要_20191114.docx（九民纪要） | https://www.court.gov.cn/zixun/xiangqing/199691.html | ✅ 已添加 |

## 说明

- 所有来源均为最高人民法院官方网站或公报，具有权威性
- 抓取脚本位于 `scripts/fetch_web_sources.py`
- 抓取的原始 HTML 缓存在 `_web_sources/html_cache/` 目录
- 转换后的文本存放在对应 sources 目录下的 .docx 旁边（以 _web 后缀区分中间产物）
