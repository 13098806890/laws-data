#!/usr/bin/env python3
"""
下载 law_content.db（GitHub Releases 附件）。

主库数据库（约 460MB）不随源码仓库分发，改为 GitHub Releases 附件发布。
本脚本从指定 repo 的 latest release 下载 law_content.db 到项目根目录。

用法：
    python3 scripts/download_db.py                  # 默认从 doxie/laws-data 拉取
    python3 scripts/download_db.py --repo user/repo # 指定仓库
    python3 scripts/download_db.py --version v2.1.0 # 指定版本（默认 latest）
    python3 scripts/download_db.py --force          # 本地已有 DB 时仍强制重新下载
    python3 scripts/download_db.py --verify         # 下载后执行 verify_db.py
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / 'law_content.db'
API_LATEST = 'https://api.github.com/repos/{repo}/releases/latest'
API_TAG = 'https://api.github.com/repos/{repo}/releases/tags/{tag}'
DEFAULT_REPO = 'doxie/laws-data'
MIN_SIZE = 100_000_000


def get_asset(repo: str, version: str | None) -> dict:
    """查询 release 元数据，返回 law_content.db 附件信息 {url, size}。"""
    url = API_LATEST.format(repo=repo) if not version else API_TAG.format(repo=repo, tag=version)
    req = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SystemExit(
                f'release 不存在：{repo}' + (f' @ {version}' if version else '（无 release）'))
        raise
    except urllib.error.URLError as e:
        raise SystemExit(f'无法访问 GitHub API：{e.reason}')
    for asset in data.get('assets', []):
        if asset['name'] == 'law_content.db':
            return {'url': asset['browser_download_url'], 'size': asset.get('size', 0)}
    raise SystemExit(f'未在 release {data.get("tag_name", version or "latest")} 中找到 law_content.db 附件')


def main():
    parser = argparse.ArgumentParser(description='Download law_content.db from GitHub Releases')
    parser.add_argument('--repo', default=DEFAULT_REPO, help='GitHub 仓库（默认 %(default)s）')
    parser.add_argument('--version', default=None, help='release tag（默认 latest）')
    parser.add_argument('--force', action='store_true', help='本地已有 DB 时仍重新下载')
    parser.add_argument('--verify', action='store_true', help='下载后运行 verify_db.py')
    args = parser.parse_args()

    if DB_PATH.exists() and DB_PATH.stat().st_size > MIN_SIZE and not args.force:
        print(f'本地已有 law_content.db（{DB_PATH.stat().st_size/1e6:.0f}MB），跳过下载'
              f'（加 --force 可强制重新下载）')
        return

    print(f'从 {args.repo} 下载 law_content.db ...')
    asset = get_asset(args.repo, args.version)
    print(f'  URL: {asset["url"]}')
    try:
        urllib.request.urlretrieve(asset['url'], DB_PATH)
    except urllib.error.URLError as e:
        raise SystemExit(f'下载失败：{e.reason}')
    except Exception as e:
        raise SystemExit(f'下载失败：{e}')

    size = DB_PATH.stat().st_size
    if asset['size'] and abs(size - asset['size']) > 1_000_000:
        DB_PATH.unlink(missing_ok=True)
        raise SystemExit(f'下载文件大小异常（本地 {size/1e6:.0f}MB vs 远端 {asset["size"]/1e6:.0f}MB），'
                         f'已删除，请重试或加 --force')
    print(f'下载完成：{DB_PATH}（{size/1e6:.0f}MB）')

    if args.verify:
        sys.path.insert(0, str(BASE_DIR / 'scripts'))
        from verify_db import main as verify
        verify()


if __name__ == '__main__':
    main()
