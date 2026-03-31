#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Maven 超期依赖自动迁移工具
===========================

功能：
  1. scan     - 扫描多模块 Maven 项目，识别超过 N 年的依赖
  2. migrate  - 自动将超期依赖迁移到 lib-expired 模块 + 本地仓库
  3. download - 下载超期 jar 到 repo-local 文件仓库
  4. report   - 生成 Excel/CSV 报告
  5. build-db - 从本地 Maven 缓存构建日期数据库文件

日期检测策略（按优先级自动切换）：
  1. 内置已知数据库（KNOWN_EXPIRED_DB）
  2. 用户自定义数据库文件（--date-db deps_dates.json）
  3. 本地 Maven 缓存 ~/.m2/repository（--m2-cache）
  4. 内网镜像 maven-metadata.xml（--mirror-url）
  5. 内网镜像 HTTP Last-Modified 头（--mirror-url 自动启用）
  6. Nexus 3 REST API（--mirror-url + --mirror-type nexus3）
  7. Maven Central Search API（默认，外网环境）

典型用法（内网）：
  # 方式 1：用本地 Maven 缓存（无需网络，最快）
  python migrate_expired_deps.py scan -d ../ --m2-cache

  # 方式 2：用内网镜像源的 metadata
  python migrate_expired_deps.py scan -d ../ --mirror-url http://nexus.corp.com/repository/maven-public

  # 方式 3：内网 Nexus 3 API（最准确）
  python migrate_expired_deps.py scan -d ../ --mirror-url http://nexus.corp.com --mirror-type nexus3

  # 方式 4：先构建日期数据库，再离线使用
  python migrate_expired_deps.py build-db --m2-cache -o deps_dates.json
  python migrate_expired_deps.py scan -d ../ --date-db deps_dates.json

典型用法（外网）：
  python migrate_expired_deps.py scan -d ../
  python migrate_expired_deps.py migrate -d ../ --dry-run

依赖：pip install requests（可选，离线模式不需要）
"""

import argparse
import copy
import csv
import json
import logging
import os
import re
import shutil
import sys
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

# 可选依赖
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────
MAVEN_NS = "http://maven.apache.org/POM/4.0.0"
NS = {"m": MAVEN_NS}
ET.register_namespace("", MAVEN_NS)
ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")

MAVEN_CENTRAL_SEARCH = "https://search.maven.org/solrsearch/select"
MAVEN_CENTRAL_REPO = "https://repo1.maven.org/maven2"

# 超期年限阈值
DEFAULT_MAX_AGE_YEARS = 3

# 已知超期依赖数据库（离线备用，避免每次都查 Maven Central）
KNOWN_EXPIRED_DB = {
    ("com.google.guava", "guava", "20.0"): "2016-10-28",
    ("com.google.guava", "guava", "23.0"): "2017-08-04",
    ("commons-collections", "commons-collections", "3.2.2"): "2015-11-13",
    ("commons-io", "commons-io", "2.6"): "2018-10-15",
    ("com.alibaba", "fastjson", "1.2.83"): "2022-05-23",
    ("log4j", "log4j", "1.2.17"): "2012-05-26",
    ("net.sf.ehcache", "ehcache", "2.10.9.2"): "2020-09-02",
    ("net.sf.ehcache", "ehcache", "2.10.6"): "2018-11-01",
    ("com.alibaba", "fastjson", "1.2.78"): "2021-09-02",
    ("mysql", "mysql-connector-java", "5.1.49"): "2020-04-27",
    ("org.apache.httpcomponents", "httpclient", "4.5.13"): "2020-09-09",
}

# ──────────────────────────────────────────────
# 日期检测策略（可插拔，支持内网环境）
# ──────────────────────────────────────────────

class DateDetector:
    """日期检测策略基类"""
    name = "base"

    def detect(self, group_id, artifact_id, version):
        """检测发布日期，返回 'YYYY-MM-DD' 字符串或 None"""
        raise NotImplementedError


class KnownDatabaseDetector(DateDetector):
    """策略 1：内置已知数据库"""
    name = "known-db"

    def detect(self, group_id, artifact_id, version):
        return KNOWN_EXPIRED_DB.get((group_id, artifact_id, version))


class CustomDatabaseDetector(DateDetector):
    """
    策略 2：用户自定义 JSON 数据库文件
    
    文件格式（deps_dates.json）：
    {
      "com.google.guava:guava:20.0": "2016-10-28",
      "commons-io:commons-io:2.6": "2018-10-15"
    }
    
    或者带注释的详细格式：
    {
      "dependencies": {
        "com.google.guava:guava:20.0": {
          "date": "2016-10-28",
          "note": "升级到 33.x"
        }
      }
    }
    """
    name = "custom-db"

    def __init__(self, db_path):
        self._db = {}
        self._load(db_path)

    def _load(self, db_path):
        path = Path(db_path)
        if not path.exists():
            LOG.warning(f"日期数据库文件不存在: {db_path}")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 支持两种格式
            if "dependencies" in data and isinstance(data["dependencies"], dict):
                for coord, info in data["dependencies"].items():
                    if isinstance(info, str):
                        self._db[coord] = info
                    elif isinstance(info, dict):
                        self._db[coord] = info.get("date", "")
            elif isinstance(data, dict):
                for coord, date_str in data.items():
                    if isinstance(date_str, str):
                        self._db[coord] = date_str
            LOG.info(f"已加载自定义日期数据库: {len(self._db)} 条记录")
        except (json.JSONDecodeError, KeyError) as e:
            LOG.warning(f"日期数据库解析失败: {e}")

    def detect(self, group_id, artifact_id, version):
        coord = f"{group_id}:{artifact_id}:{version}"
        return self._db.get(coord)


class LocalM2CacheDetector(DateDetector):
    """
    策略 3：扫描本地 Maven 缓存 (~/.m2/repository)
    
    Maven 下载 jar 时通常保留原始文件的修改时间，
    该时间接近发布日期（可能有几天偏差，但足够判断是否超期）。
    
    如果 jar 附带 _remote.repositories 标记文件，也会参考。
    """
    name = "m2-cache"

    def __init__(self, m2_path=None):
        if m2_path:
            self._m2_repo = Path(m2_path)
        else:
            # 自动检测 ~/.m2/repository
            home = Path.home()
            self._m2_repo = home / ".m2" / "repository"
        if not self._m2_repo.exists():
            LOG.warning(f"Maven 本地缓存不存在: {self._m2_repo}")

    def detect(self, group_id, artifact_id, version):
        if not self._m2_repo.exists():
            return None

        group_path = group_id.replace(".", os.sep)
        artifact_dir = self._m2_repo / group_path / artifact_id / version
        if not artifact_dir.exists():
            return None

        # 优先查 jar，其次 pom
        jar_file = artifact_dir / f"{artifact_id}-{version}.jar"
        pom_file = artifact_dir / f"{artifact_id}-{version}.pom"

        target = jar_file if jar_file.exists() else (pom_file if pom_file.exists() else None)
        if target is None:
            return None

        mtime = target.stat().st_mtime
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


class MavenMetadataDetector(DateDetector):
    """
    策略 4：从 Maven 仓库（镜像源）的 maven-metadata.xml 获取日期
    
    所有 Maven 仓库管理器（Nexus、Artifactory、普通 HTTP 文件服务器）都提供此文件。
    路径: {repo-url}/{groupPath}/{artifactId}/maven-metadata.xml
    
    内容示例：
    <metadata>
      <versioning>
        <versions>
          <version>20.0</version>
        </versions>
        <lastUpdated>20161028035018</lastUpdated>
      </versioning>
    </metadata>
    
    注意：lastUpdated 是最近一个版本的更新时间，不精确对应特定版本。
    更精确的做法是查询 version 级别的 maven-metadata.xml（如果有的话）。
    """
    name = "maven-metadata"

    def __init__(self, mirror_url):
        self._mirror_url = mirror_url.rstrip("/")

    def detect(self, group_id, artifact_id, version):
        if not HAS_REQUESTS:
            return None

        group_path = group_id.replace(".", "/")

        # 尝试 version 级别的 metadata（部分仓库提供）
        ver_metadata_url = (
            f"{self._mirror_url}/{group_path}/{artifact_id}"
            f"/{version}/maven-metadata.xml"
        )
        date = self._parse_metadata_url(ver_metadata_url)
        if date:
            return date

        # 回退到 artifact 级别的 metadata
        artifact_metadata_url = (
            f"{self._mirror_url}/{group_path}/{artifact_id}/maven-metadata.xml"
        )
        return self._parse_metadata_url(artifact_metadata_url)

    def _parse_metadata_url(self, url):
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                return None
            root = ET.fromstring(resp.content)
            # 查找 <lastUpdated> 标签（无命名空间）
            last_updated = root.findtext(".//lastUpdated")
            if last_updated and len(last_updated) >= 8:
                # 格式: 20161028035018 → 2016-10-28
                return f"{last_updated[:4]}-{last_updated[4:6]}-{last_updated[6:8]}"
        except Exception as e:
            LOG.debug(f"metadata 查询失败 {url}: {e}")
        return None


class HttpLastModifiedDetector(DateDetector):
    """
    策略 5：通过 HTTP HEAD 请求获取 artifact 的 Last-Modified 日期
    
    几乎所有 HTTP 服务器都返回 Last-Modified 头。
    对镜像源发出 HEAD 请求（不下载内容），读取 Last-Modified 响应头。
    """
    name = "http-last-modified"

    def __init__(self, mirror_url):
        self._mirror_url = mirror_url.rstrip("/")

    def detect(self, group_id, artifact_id, version):
        if not HAS_REQUESTS:
            return None

        group_path = group_id.replace(".", "/")
        # 优先查 jar，再查 pom
        for ext in (".jar", ".pom"):
            url = (
                f"{self._mirror_url}/{group_path}/{artifact_id}"
                f"/{version}/{artifact_id}-{version}{ext}"
            )
            date = self._head_last_modified(url)
            if date:
                return date
        return None

    def _head_last_modified(self, url):
        try:
            resp = requests.head(url, timeout=10, allow_redirects=True)
            if resp.status_code != 200:
                return None
            lm = resp.headers.get("Last-Modified")
            if lm:
                # 格式: "Fri, 28 Oct 2016 03:50:18 GMT"
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(lm)
                return dt.strftime("%Y-%m-%d")
        except Exception as e:
            LOG.debug(f"HEAD 查询失败 {url}: {e}")
        return None


class Nexus3ApiDetector(DateDetector):
    """
    策略 6：Nexus 3 REST API
    
    Nexus 3 提供 /service/rest/v1/search 接口，类似 Maven Central Search。
    URL: {nexus-url}/service/rest/v1/search?group={g}&name={a}&version={v}
    
    响应中 items[].assets[].lastModified 包含精确时间。
    """
    name = "nexus3-api"

    def __init__(self, nexus_url, repository=None):
        self._nexus_url = nexus_url.rstrip("/")
        self._repository = repository  # 如 "maven-public"

    def detect(self, group_id, artifact_id, version):
        if not HAS_REQUESTS:
            return None
        try:
            params = {
                "group": group_id,
                "name": artifact_id,
                "version": version,
            }
            if self._repository:
                params["repository"] = self._repository

            url = f"{self._nexus_url}/service/rest/v1/search"
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            items = data.get("items", [])
            if items:
                # 取第一个 asset 的 lastModified
                assets = items[0].get("assets", [])
                if assets:
                    lm = assets[0].get("lastModified", "")
                    # 格式: "2016-10-28T03:50:18.000+00:00"
                    if lm and len(lm) >= 10:
                        return lm[:10]
            time.sleep(0.2)
        except Exception as e:
            LOG.debug(f"Nexus API 查询失败: {e}")
        return None


class MavenCentralSearchDetector(DateDetector):
    """策略 7：Maven Central Search API（外网环境）"""
    name = "maven-central"

    def detect(self, group_id, artifact_id, version):
        if not HAS_REQUESTS:
            return None
        try:
            params = {
                "q": f'g:"{group_id}" AND a:"{artifact_id}" AND v:"{version}"',
                "rows": 1,
                "wt": "json",
            }
            resp = requests.get(MAVEN_CENTRAL_SEARCH, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("response", {}).get("docs", [])
                if docs:
                    ts = docs[0].get("timestamp", 0)
                    if ts:
                        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
            time.sleep(0.3)
        except Exception as e:
            LOG.debug(f"Maven Central 查询失败 {group_id}:{artifact_id}:{version}: {e}")
        return None


class DateDetectorChain:
    """
    日期检测策略链
    
    按优先级逐个尝试，第一个成功返回的即为最终结果。
    """

    def __init__(self):
        self._detectors = []

    def add(self, detector):
        self._detectors.append(detector)
        return self

    def detect(self, group_id, artifact_id, version):
        for detector in self._detectors:
            result = detector.detect(group_id, artifact_id, version)
            if result:
                LOG.debug(f"  日期来源 [{detector.name}]: "
                          f"{group_id}:{artifact_id}:{version} → {result}")
                return result
        return None

    def describe(self):
        return " → ".join(d.name for d in self._detectors)


def build_date_db_from_m2(m2_path=None, project_dir=None, output_path=None):
    """
    从本地 Maven 缓存构建日期数据库文件
    
    如果指定了 project_dir，只扫描该项目用到的依赖。
    否则扫描整个 ~/.m2/repository（可能很大）。
    """
    m2_repo = Path(m2_path) if m2_path else Path.home() / ".m2" / "repository"
    if not m2_repo.exists():
        LOG.error(f"Maven 缓存不存在: {m2_repo}")
        return

    db = {}

    if project_dir:
        # 只扫描项目依赖
        scanner = ProjectScanner(project_dir)
        scanner.scan()
        unique = scanner._deduplicate()
        LOG.info(f"从项目中发现 {len(unique)} 个唯一依赖，开始查询本地缓存...")

        detector = LocalM2CacheDetector(str(m2_repo))
        for dep in unique:
            if dep.version == "(inherited)":
                continue
            date = detector.detect(dep.group_id, dep.artifact_id, dep.version)
            if date:
                coord = f"{dep.group_id}:{dep.artifact_id}:{dep.version}"
                db[coord] = date
    else:
        # 扫描整个 m2 缓存
        LOG.info(f"扫描整个 Maven 缓存: {m2_repo}")
        count = 0
        for root, dirs, files in os.walk(m2_repo):
            for f in files:
                if not f.endswith(".jar") or f.endswith("-sources.jar") or f.endswith("-javadoc.jar"):
                    continue
                jar_path = Path(root) / f
                # 从路径反推坐标: .m2/repo/{g}/{a}/{v}/{a}-{v}.jar
                try:
                    rel = jar_path.relative_to(m2_repo)
                    parts = list(rel.parts)
                    if len(parts) < 4:
                        continue
                    version = parts[-2]
                    artifact_id = parts[-3]
                    group_id = ".".join(parts[:-3])
                    expected_name = f"{artifact_id}-{version}.jar"
                    if f != expected_name:
                        continue
                    mtime = jar_path.stat().st_mtime
                    date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                    coord = f"{group_id}:{artifact_id}:{version}"
                    db[coord] = date_str
                    count += 1
                except (ValueError, IndexError):
                    continue
        LOG.info(f"共扫描到 {count} 个 jar 文件")

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
        LOG.info(f"日期数据库已保存: {output_path} ({len(db)} 条记录)")
    else:
        # 输出到控制台
        print(json.dumps(db, indent=2, ensure_ascii=False))

    return db


LOG = logging.getLogger("migrate")

# Windows 终端 GBK 编码兼容
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ──────────────────────────────────────────────
# XML 工具函数
# ──────────────────────────────────────────────

def _tag(local_name):
    """带命名空间的标签名"""
    return f"{{{MAVEN_NS}}}{local_name}"


def _find_text(element, path):
    """安全地查询元素文本"""
    node = element.find(path, NS)
    return node.text.strip() if node is not None and node.text else None


def _parse_pom(pom_path):
    """解析 POM 文件，返回 (tree, root)"""
    parser = ET.XMLParser(encoding="utf-8")
    tree = ET.parse(str(pom_path), parser)
    root = tree.getroot()
    return tree, root


def _write_pom(tree, pom_path):
    """安全写出 POM（先备份）"""
    backup = Path(str(pom_path) + ".bak")
    if not backup.exists():
        shutil.copy2(pom_path, backup)
    tree.write(str(pom_path), xml_declaration=True, encoding="utf-8")
    # 修正自闭合标签和格式
    _pretty_fix(pom_path)


def _pretty_fix(pom_path):
    """简单修正 ET 输出的格式问题"""
    content = Path(pom_path).read_text(encoding="utf-8")
    # 确保有换行
    content = content.replace("><", ">\n<")
    # 不做过度格式化，保持可读即可
    # 这里只做 namespace 声明修正
    if 'xmlns:ns0=' in content:
        content = content.replace('ns0:', '').replace('xmlns:ns0=', 'xmlns=')
    Path(pom_path).write_text(content, encoding="utf-8")


# ──────────────────────────────────────────────
# 属性解析
# ──────────────────────────────────────────────

class PropertyResolver:
    """解析 Maven ${property} 引用"""

    def __init__(self):
        self.properties = {}

    def load_from_pom(self, root):
        """从 POM 的 <properties> 节点加载"""
        props_node = root.find("m:properties", NS)
        if props_node is not None:
            for child in props_node:
                # 去掉命名空间
                local_name = child.tag.replace(f"{{{MAVEN_NS}}}", "")
                if child.text:
                    self.properties[local_name] = child.text.strip()

    def resolve(self, value):
        """解析 ${xxx} 引用，最多递归 5 层"""
        if not value:
            return value
        for _ in range(5):
            match = re.search(r'\$\{(.+?)\}', value)
            if not match:
                break
            key = match.group(1)
            replacement = self.properties.get(key, match.group(0))
            value = value.replace(match.group(0), replacement)
        return value


# ──────────────────────────────────────────────
# 依赖扫描器
# ──────────────────────────────────────────────

class DependencyInfo:
    """单个依赖信息"""
    def __init__(self, group_id, artifact_id, version, scope=None,
                 pom_path=None, section="dependencies"):
        self.group_id = group_id
        self.artifact_id = artifact_id
        self.version = version
        self.scope = scope
        self.pom_path = pom_path
        self.section = section  # "dependencies" 或 "dependencyManagement"
        # 以下字段在分析后填充
        self.release_date = None
        self.age_days = None
        self.is_expired = False
        self.latest_version = None

    @property
    def coord(self):
        return f"{self.group_id}:{self.artifact_id}:{self.version}"

    @property
    def key(self):
        return (self.group_id, self.artifact_id, self.version)

    def __repr__(self):
        expired_mark = " ⚠️EXPIRED" if self.is_expired else ""
        return f"{self.coord} [{self.pom_path}]{expired_mark}"


class ProjectScanner:
    """扫描多模块 Maven 项目"""

    def __init__(self, project_dir, max_age_years=DEFAULT_MAX_AGE_YEARS,
                 date_chain=None):
        self.project_dir = Path(project_dir).resolve()
        self.max_age_years = max_age_years
        self.cutoff_date = datetime.now() - timedelta(days=max_age_years * 365)
        self.resolver = PropertyResolver()
        self.all_deps = []
        self.expired_deps = []
        self.internal_artifacts = set()
        self._date_cache = {}
        # 日期检测策略链
        self._date_chain = date_chain or self._default_chain()

    @staticmethod
    def _default_chain():
        """默认策略链：内置数据库 → Maven Central"""
        chain = DateDetectorChain()
        chain.add(KnownDatabaseDetector())
        if HAS_REQUESTS:
            chain.add(MavenCentralSearchDetector())
        return chain

    def scan(self):
        """执行全量扫描"""
        LOG.info("=" * 60)
        LOG.info(f"扫描项目: {self.project_dir}")
        LOG.info(f"超期阈值: {self.max_age_years} 年 (截止 {self.cutoff_date.strftime('%Y-%m-%d')})")
        LOG.info(f"检测策略: {self._date_chain.describe()}")
        LOG.info("=" * 60)

        # 1. 找到所有 pom.xml
        pom_files = self._find_pom_files()
        LOG.info(f"发现 {len(pom_files)} 个 POM 文件")

        # 2. 第一遍：收集内部模块坐标 + 属性
        for pom in pom_files:
            self._collect_internal_artifact(pom)

        # 3. 第二遍：收集所有外部依赖
        for pom in pom_files:
            self._collect_dependencies(pom)

        LOG.info(f"共发现 {len(self.all_deps)} 个外部依赖声明")

        # 4. 去重，按坐标聚合
        unique_deps = self._deduplicate()
        LOG.info(f"去重后 {len(unique_deps)} 个唯一依赖")

        # 5. 查询每个依赖的发布日期
        for dep in unique_deps:
            self._check_expiry(dep)

        # 6. 标记所有实例
        expired_keys = {d.key for d in unique_deps if d.is_expired}
        for dep in self.all_deps:
            if dep.key in expired_keys:
                dep.is_expired = True
                matched = [d for d in unique_deps if d.key == dep.key][0]
                dep.release_date = matched.release_date
                dep.age_days = matched.age_days

        self.expired_deps = [d for d in self.all_deps if d.is_expired]
        return self.expired_deps

    def _find_pom_files(self):
        """递归查找所有 pom.xml（跳过 target/, repo-local/, .git/）"""
        pom_files = []
        for root, dirs, files in os.walk(self.project_dir):
            # 跳过这些目录
            dirs[:] = [d for d in dirs if d not in (
                'target', '.git', '.svn', 'node_modules', 'repo-local',
                '.idea', '.settings'
            )]
            if 'pom.xml' in files:
                pom_files.append(Path(root) / 'pom.xml')
        return sorted(pom_files)

    def _collect_internal_artifact(self, pom_path):
        """收集内部模块 artifactId（用于排除）"""
        try:
            _, root = _parse_pom(pom_path)
            group_id = _find_text(root, "m:groupId")
            artifact_id = _find_text(root, "m:artifactId")
            # 如果没有 groupId，继承 parent 的
            if not group_id:
                parent = root.find("m:parent", NS)
                if parent is not None:
                    group_id = _find_text(parent, "m:groupId")
            if group_id and artifact_id:
                self.internal_artifacts.add((group_id, artifact_id))
            # 同时收集属性
            self.resolver.load_from_pom(root)
        except ET.ParseError as e:
            LOG.warning(f"解析失败: {pom_path}: {e}")

    def _collect_dependencies(self, pom_path):
        """收集一个 POM 中的所有外部依赖"""
        try:
            _, root = _parse_pom(pom_path)
        except ET.ParseError as e:
            LOG.warning(f"解析失败: {pom_path}: {e}")
            return

        rel_path = pom_path.relative_to(self.project_dir)

        # 从 <dependencies> 收集
        deps_node = root.find("m:dependencies", NS)
        if deps_node is not None:
            for dep in deps_node.findall("m:dependency", NS):
                info = self._parse_dependency(dep, str(rel_path), "dependencies")
                if info:
                    self.all_deps.append(info)

        # 从 <dependencyManagement><dependencies> 收集
        dm = root.find("m:dependencyManagement", NS)
        if dm is not None:
            dm_deps = dm.find("m:dependencies", NS)
            if dm_deps is not None:
                for dep in dm_deps.findall("m:dependency", NS):
                    info = self._parse_dependency(dep, str(rel_path), "dependencyManagement")
                    if info:
                        self.all_deps.append(info)

    def _parse_dependency(self, dep_node, pom_path, section):
        """解析一个 <dependency> 节点"""
        group_id = _find_text(dep_node, "m:groupId")
        artifact_id = _find_text(dep_node, "m:artifactId")
        version = _find_text(dep_node, "m:version")
        scope = _find_text(dep_node, "m:scope")

        if not group_id or not artifact_id:
            return None

        # 跳过内部模块
        if (group_id, artifact_id) in self.internal_artifacts:
            return None

        # 跳过 test/provided scope
        if scope in ("test", "provided"):
            return None

        # 解析属性引用
        if version:
            version = self.resolver.resolve(version)

        # 没有版本（从 parent 继承）则标记
        if not version:
            version = "(inherited)"

        return DependencyInfo(
            group_id=group_id,
            artifact_id=artifact_id,
            version=version,
            scope=scope,
            pom_path=pom_path,
            section=section,
        )

    def _deduplicate(self):
        """按 (groupId, artifactId, version) 去重"""
        seen = {}
        for dep in self.all_deps:
            if dep.key not in seen and dep.version != "(inherited)":
                seen[dep.key] = dep
        return list(seen.values())

    def _check_expiry(self, dep):
        """检查单个依赖是否超期（通过策略链）"""
        key = dep.key

        # 先查本地缓存（避免重复查询）
        if key in self._date_cache:
            dep.release_date = self._date_cache[key]
        elif dep.version != "(inherited)":
            # 通过策略链检测
            dep.release_date = self._date_chain.detect(
                dep.group_id, dep.artifact_id, dep.version
            )
            self._date_cache[key] = dep.release_date

        if dep.release_date:
            try:
                release_dt = datetime.strptime(dep.release_date, "%Y-%m-%d")
                dep.age_days = (datetime.now() - release_dt).days
                if release_dt < self.cutoff_date:
                    dep.is_expired = True
            except ValueError:
                pass


# ──────────────────────────────────────────────
# 迁移执行器
# ──────────────────────────────────────────────

class MigrationExecutor:
    """执行超期依赖迁移"""

    def __init__(self, project_dir, scanner, mirror_url=None):
        self.project_dir = Path(project_dir).resolve()
        self.scanner = scanner
        self.lib_expired_pom = self.project_dir / "lib-expired" / "pom.xml"
        self.repo_local_dir = self.project_dir / "repo-local"
        self.parent_pom = self.project_dir / "pom.xml"
        self.mirror_url = mirror_url.rstrip("/") if mirror_url else None

    def migrate(self, dry_run=False):
        """执行迁移"""
        expired = self.scanner.expired_deps
        if not expired:
            LOG.info("没有发现超期依赖，无需迁移。")
            return

        # 按 (groupId, artifactId, version) 聚合
        unique_expired = {}
        for dep in expired:
            if dep.key not in unique_expired:
                unique_expired[dep.key] = dep

        LOG.info(f"\n{'='*60}")
        LOG.info(f"{'[DRY RUN] ' if dry_run else ''}开始迁移 {len(unique_expired)} 个超期依赖")
        LOG.info(f"{'='*60}")

        for dep in unique_expired.values():
            self._migrate_one(dep, dry_run)

        if not dry_run:
            LOG.info("\n✅ 迁移完成！请执行 mvn clean install 验证。")
        else:
            LOG.info("\n📋 DRY RUN 完成，未做任何修改。")

    def _migrate_one(self, dep, dry_run):
        """迁移一个依赖"""
        LOG.info(f"\n--- 迁移: {dep.coord} (发布: {dep.release_date}, {dep.age_days}天前) ---")

        # Step 1: 确保依赖在 lib-expired/pom.xml 中
        if not self._is_in_lib_expired(dep):
            LOG.info(f"  → 添加到 lib-expired/pom.xml")
            if not dry_run:
                self._add_to_lib_expired(dep)
        else:
            LOG.info(f"  ✓ 已存在于 lib-expired/pom.xml")

        # Step 2: 确保版本在 parent dependencyManagement 中
        LOG.info(f"  → 检查 parent dependencyManagement")
        # 这通常已经存在，因为范例项目版本都在 parent

        # Step 3: 从各业务模块的 <dependencies> 中移除（如果不在 common 的传递路径上）
        occurrences = [d for d in self.scanner.all_deps
                       if d.key == dep.key and d.section == "dependencies"]
        for occ in occurrences:
            pom_rel = occ.pom_path
            # 跳过 lib-expired 自身和 common
            if "lib-expired" in pom_rel or "common" in pom_rel:
                continue
            LOG.info(f"  → 从 {pom_rel} 移除直接依赖声明")
            if not dry_run:
                self._remove_dep_from_pom(occ)

        # Step 4: 下载到本地仓库
        if dep.version != "(inherited)":
            LOG.info(f"  → 下载到 repo-local/")
            if not dry_run:
                self._download_to_repo_local(dep)

    def _is_in_lib_expired(self, dep):
        """检查 lib-expired/pom.xml 是否已包含该依赖"""
        if not self.lib_expired_pom.exists():
            return False
        try:
            _, root = _parse_pom(self.lib_expired_pom)
            deps_node = root.find("m:dependencies", NS)
            if deps_node is None:
                return False
            for d in deps_node.findall("m:dependency", NS):
                g = _find_text(d, "m:groupId")
                a = _find_text(d, "m:artifactId")
                if g == dep.group_id and a == dep.artifact_id:
                    return True
        except ET.ParseError:
            pass
        return False

    def _add_to_lib_expired(self, dep):
        """将依赖添加到 lib-expired/pom.xml"""
        if not self.lib_expired_pom.exists():
            self._create_lib_expired_pom()

        tree, root = _parse_pom(self.lib_expired_pom)
        deps_node = root.find("m:dependencies", NS)
        if deps_node is None:
            deps_node = ET.SubElement(root, _tag("dependencies"))

        # 创建 dependency 元素
        dep_elem = ET.SubElement(deps_node, _tag("dependency"))
        g = ET.SubElement(dep_elem, _tag("groupId"))
        g.text = dep.group_id
        a = ET.SubElement(dep_elem, _tag("artifactId"))
        a.text = dep.artifact_id
        # 版本由 parent dependencyManagement 管理，不写死

        _write_pom(tree, self.lib_expired_pom)

    def _create_lib_expired_pom(self):
        """创建 lib-expired/pom.xml 骨架"""
        self.lib_expired_pom.parent.mkdir(parents=True, exist_ok=True)
        content = '''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>demo-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </parent>

    <artifactId>lib-expired</artifactId>
    <packaging>pom</packaging>
    <name>Lib Expired - 超期依赖聚合（自动生成）</name>

    <dependencies>
    </dependencies>
</project>
'''
        self.lib_expired_pom.write_text(content, encoding="utf-8")

    def _remove_dep_from_pom(self, dep):
        """从指定 POM 的 <dependencies> 中移除一个依赖"""
        pom_path = self.project_dir / dep.pom_path
        try:
            tree, root = _parse_pom(pom_path)
        except (ET.ParseError, FileNotFoundError):
            return

        deps_node = root.find("m:dependencies", NS)
        if deps_node is None:
            return

        for d in deps_node.findall("m:dependency", NS):
            g = _find_text(d, "m:groupId")
            a = _find_text(d, "m:artifactId")
            if g == dep.group_id and a == dep.artifact_id:
                deps_node.remove(d)
                LOG.info(f"    ✓ 已移除 {dep.group_id}:{dep.artifact_id} from {dep.pom_path}")
                break

        _write_pom(tree, pom_path)

    def _download_to_repo_local(self, dep):
        """下载 jar 和 pom 到本地文件仓库"""
        if not HAS_REQUESTS:
            LOG.warning("    ⚠ 需要 requests 库才能下载: pip install requests")
            return

        # Maven 仓库路径: groupId 转目录 / artifactId / version / artifact-version.jar
        group_path = dep.group_id.replace(".", "/")
        base_dir = self.repo_local_dir / group_path / dep.artifact_id / dep.version
        base_dir.mkdir(parents=True, exist_ok=True)

        base_name = f"{dep.artifact_id}-{dep.version}"
        repo_base = self.mirror_url or MAVEN_CENTRAL_REPO
        base_url = f"{repo_base}/{group_path}/{dep.artifact_id}/{dep.version}"

        for ext in (".jar", ".pom"):
            target_file = base_dir / f"{base_name}{ext}"
            if target_file.exists():
                LOG.info(f"    ✓ 已存在: {target_file.name}")
                continue

            url = f"{base_url}/{base_name}{ext}"
            try:
                LOG.info(f"    ↓ 下载: {url}")
                resp = requests.get(url, timeout=30, stream=True)
                if resp.status_code == 200:
                    with open(target_file, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    LOG.info(f"    ✓ 已保存: {target_file.name} ({target_file.stat().st_size:,} bytes)")
                else:
                    LOG.warning(f"    ⚠ 下载失败 ({resp.status_code}): {url}")
            except Exception as e:
                LOG.warning(f"    ⚠ 下载异常: {e}")

            time.sleep(0.2)  # 限流


# ──────────────────────────────────────────────
# 报告生成器
# ──────────────────────────────────────────────

def generate_report(scanner, output_path):
    """生成 CSV 报告"""
    rows = []
    for dep in scanner.all_deps:
        rows.append({
            "groupId": dep.group_id,
            "artifactId": dep.artifact_id,
            "version": dep.version,
            "scope": dep.scope or "",
            "pom_path": dep.pom_path,
            "section": dep.section,
            "release_date": dep.release_date or "",
            "age_days": dep.age_days or "",
            "is_expired": "YES" if dep.is_expired else "",
        })

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [])
        writer.writeheader()
        writer.writerows(rows)

    LOG.info(f"报告已生成: {output_path} ({len(rows)} 行)")


# ──────────────────────────────────────────────
# 控制台输出
# ──────────────────────────────────────────────

def print_scan_result(scanner):
    """漂亮地打印扫描结果"""
    expired = scanner.expired_deps
    if not expired:
        print("\n✅ 未发现超期依赖。")
        return

    # 按 POM 分组
    by_pom = {}
    for dep in expired:
        by_pom.setdefault(dep.pom_path, []).append(dep)

    print(f"\n{'='*70}")
    print(f"⚠️  发现 {len(expired)} 处超期依赖声明")
    print(f"{'='*70}")

    # 先显示去重汇总
    unique = {}
    for dep in expired:
        if dep.key not in unique:
            unique[dep.key] = dep

    print(f"\n📦 唯一超期包 ({len(unique)} 个):")
    print(f"{'─'*70}")
    print(f"  {'坐标':<50} {'发布日期':<12} {'年龄'}")
    print(f"{'─'*70}")
    for dep in sorted(unique.values(), key=lambda d: d.age_days or 0, reverse=True):
        age_str = f"{dep.age_days // 365}年{(dep.age_days % 365) // 30}月" if dep.age_days else "未知"
        print(f"  {dep.coord:<50} {dep.release_date or '?':<12} {age_str}")

    # 再显示每个 POM 的明细
    print(f"\n📂 各模块明细:")
    print(f"{'─'*70}")
    for pom, deps in sorted(by_pom.items()):
        print(f"\n  📄 {pom}")
        for dep in deps:
            section_mark = "⚙" if dep.section == "dependencyManagement" else "📎"
            print(f"     {section_mark} {dep.group_id}:{dep.artifact_id}:{dep.version}")

    print(f"\n{'─'*70}")
    print(f"💡 运行 migrate 命令自动迁移: python {sys.argv[0]} migrate --project-dir <path>")
    print()


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def _add_common_args(parser):
    """为所有子命令添加通用参数"""
    parser.add_argument("--project-dir", "-d", required=True, help="项目根目录")
    parser.add_argument("--max-age", type=int, default=DEFAULT_MAX_AGE_YEARS,
                        help=f"超期年限阈值 (默认: {DEFAULT_MAX_AGE_YEARS})")
    parser.add_argument("--offline", action="store_true",
                        help="离线模式（禁用所有网络请求）")
    # 内网镜像源相关
    parser.add_argument("--mirror-url", metavar="URL",
                        help="内网 Maven 镜像源地址 (如 http://nexus.corp.com/repository/maven-public)")
    parser.add_argument("--mirror-type", choices=["auto", "nexus3", "generic"],
                        default="auto",
                        help="镜像源类型: auto=自动探测, nexus3=Nexus3 API, generic=仅用metadata+header (默认: auto)")
    parser.add_argument("--nexus-repo", metavar="NAME",
                        help="Nexus 3 仓库名 (如 maven-public，仅 --mirror-type nexus3 时有效)")
    # 日期数据库
    parser.add_argument("--date-db", metavar="FILE",
                        help="自定义日期数据库 JSON 文件路径")
    # 本地缓存
    parser.add_argument("--m2-cache", action="store_true",
                        help="启用本地 Maven 缓存 (~/.m2/repository) 日期检测")
    parser.add_argument("--m2-path", metavar="DIR",
                        help="自定义 Maven 本地缓存路径 (默认: ~/.m2/repository)")


def _build_date_chain(args):
    """根据 CLI 参数构建日期检测策略链"""
    chain = DateDetectorChain()

    # 1. 始终包含内置数据库（最快、无开销）
    chain.add(KnownDatabaseDetector())

    # 2. 用户自定义数据库
    if getattr(args, "date_db", None):
        chain.add(CustomDatabaseDetector(args.date_db))

    # 3. 本地 Maven 缓存
    if getattr(args, "m2_cache", False) or getattr(args, "m2_path", None):
        chain.add(LocalM2CacheDetector(getattr(args, "m2_path", None)))

    # 以下策略需要网络
    if not getattr(args, "offline", False) and HAS_REQUESTS:
        mirror_url = getattr(args, "mirror_url", None)
        mirror_type = getattr(args, "mirror_type", "auto")

        if mirror_url:
            # 4. Nexus 3 API
            if mirror_type == "nexus3":
                chain.add(Nexus3ApiDetector(mirror_url, getattr(args, "nexus_repo", None)))
            elif mirror_type == "auto":
                # 自动探测：尝试 Nexus 3 API 端点
                chain.add(Nexus3ApiDetector(mirror_url, getattr(args, "nexus_repo", None)))

            # 5. maven-metadata.xml（通用，所有仓库都支持）
            chain.add(MavenMetadataDetector(mirror_url))

            # 6. HTTP Last-Modified 头（通用兜底）
            chain.add(HttpLastModifiedDetector(mirror_url))
        else:
            # 无镜像源 URL → 用 Maven Central（外网环境）
            chain.add(MavenCentralSearchDetector())

    return chain


def main():
    parser = argparse.ArgumentParser(
        description="Maven 超期依赖自动迁移工具（支持内网环境）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例（外网）:
  %(prog)s scan    -d ./demo-expired-deps
  %(prog)s migrate -d ./demo-expired-deps --dry-run

示例（内网 - 本地 Maven 缓存）:
  %(prog)s scan -d ./ --m2-cache
  %(prog)s scan -d ./ --m2-cache --m2-path D:/maven-repo

示例（内网 - 镜像源）:
  %(prog)s scan -d ./ --mirror-url http://nexus.corp.com/repository/maven-public
  %(prog)s scan -d ./ --mirror-url http://nexus.corp.com --mirror-type nexus3

示例（内网 - 日期数据库）:
  %(prog)s build-db --m2-cache -o deps_dates.json
  %(prog)s build-db --m2-cache -d ./ -o deps_dates.json
  %(prog)s scan -d ./ --date-db deps_dates.json
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = subparsers.add_parser("scan", help="扫描超期依赖")
    _add_common_args(p_scan)

    # migrate
    p_migrate = subparsers.add_parser("migrate", help="执行迁移")
    _add_common_args(p_migrate)
    p_migrate.add_argument("--dry-run", action="store_true", help="仅预览，不执行")

    # download
    p_download = subparsers.add_parser("download", help="仅下载超期 jar 到本地仓库")
    _add_common_args(p_download)

    # report
    p_report = subparsers.add_parser("report", help="生成报告")
    _add_common_args(p_report)
    p_report.add_argument("--output", "-o", default="expired_deps_report.csv")

    # build-db（新命令）
    p_build = subparsers.add_parser("build-db",
                                     help="从本地 Maven 缓存构建日期数据库")
    p_build.add_argument("--project-dir", "-d", default=None,
                         help="项目根目录（指定则只扫描项目依赖，否则扫描全部缓存）")
    p_build.add_argument("--m2-cache", action="store_true", default=True,
                         help="使用本地 Maven 缓存（默认启用）")
    p_build.add_argument("--m2-path", metavar="DIR",
                         help="自定义 Maven 本地缓存路径")
    p_build.add_argument("--output", "-o", default=None,
                         help="输出 JSON 文件路径（不指定则输出到控制台）")
    p_build.add_argument("--mirror-url", metavar="URL",
                         help="同时从镜像源补充日期数据")
    p_build.add_argument("--offline", action="store_true")

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # offline 模式禁用 requests
    global HAS_REQUESTS
    if getattr(args, "offline", False):
        HAS_REQUESTS = False
        LOG.info("📡 离线模式：禁用所有网络请求")

    # build-db 命令特殊处理
    if args.command == "build-db":
        build_date_db_from_m2(
            m2_path=getattr(args, "m2_path", None),
            project_dir=getattr(args, "project_dir", None),
            output_path=getattr(args, "output", None),
        )
        return

    # 构建策略链
    date_chain = _build_date_chain(args)
    LOG.info(f"📡 日期检测策略链: {date_chain.describe()}")

    # 扫描
    scanner = ProjectScanner(args.project_dir, args.max_age,
                             date_chain=date_chain)
    scanner.scan()

    if args.command == "scan":
        print_scan_result(scanner)

    elif args.command == "migrate":
        print_scan_result(scanner)
        mirror = getattr(args, "mirror_url", None)
        executor = MigrationExecutor(args.project_dir, scanner, mirror_url=mirror)
        executor.migrate(dry_run=args.dry_run)

    elif args.command == "download":
        print_scan_result(scanner)
        mirror = getattr(args, "mirror_url", None)
        executor = MigrationExecutor(args.project_dir, scanner, mirror_url=mirror)
        for dep in scanner.expired_deps:
            if dep.version != "(inherited)":
                executor._download_to_repo_local(dep)

    elif args.command == "report":
        generate_report(scanner, args.output)
        print_scan_result(scanner)


if __name__ == "__main__":
    main()
