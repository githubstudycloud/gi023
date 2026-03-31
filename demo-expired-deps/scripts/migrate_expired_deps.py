#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Maven 超期依赖自动迁移工具
===========================

功能：
  1. scan   - 扫描多模块 Maven 项目，识别超过 N 年的依赖
  2. migrate - 自动将超期依赖迁移到 lib-expired 模块 + 本地仓库
  3. download - 下载超期 jar 到 repo-local 文件仓库
  4. report  - 生成 Excel/CSV 报告

用法：
  python migrate_expired_deps.py scan    --project-dir ../
  python migrate_expired_deps.py migrate --project-dir ../ --dry-run
  python migrate_expired_deps.py migrate --project-dir ../
  python migrate_expired_deps.py download --project-dir ../
  python migrate_expired_deps.py report  --project-dir ../ --output report.csv

依赖：pip install requests lxml
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

    def __init__(self, project_dir, max_age_years=DEFAULT_MAX_AGE_YEARS):
        self.project_dir = Path(project_dir).resolve()
        self.max_age_years = max_age_years
        self.cutoff_date = datetime.now() - timedelta(days=max_age_years * 365)
        self.resolver = PropertyResolver()
        self.all_deps = []
        self.expired_deps = []
        self.internal_artifacts = set()
        self._date_cache = {}

    def scan(self):
        """执行全量扫描"""
        LOG.info("=" * 60)
        LOG.info(f"扫描项目: {self.project_dir}")
        LOG.info(f"超期阈值: {self.max_age_years} 年 (截止 {self.cutoff_date.strftime('%Y-%m-%d')})")
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
        """检查单个依赖是否超期"""
        key = dep.key

        # 先查本地缓存
        if key in self._date_cache:
            dep.release_date = self._date_cache[key]
        # 再查已知数据库
        elif key in KNOWN_EXPIRED_DB:
            dep.release_date = KNOWN_EXPIRED_DB[key]
            self._date_cache[key] = dep.release_date
        # 最后查 Maven Central
        elif HAS_REQUESTS and dep.version != "(inherited)":
            dep.release_date = self._query_maven_central(dep)
            self._date_cache[key] = dep.release_date

        if dep.release_date:
            try:
                release_dt = datetime.strptime(dep.release_date, "%Y-%m-%d")
                dep.age_days = (datetime.now() - release_dt).days
                if release_dt < self.cutoff_date:
                    dep.is_expired = True
            except ValueError:
                pass

    def _query_maven_central(self, dep):
        """通过 Maven Central Search API 查询发布日期"""
        try:
            params = {
                "q": f'g:"{dep.group_id}" AND a:"{dep.artifact_id}" AND v:"{dep.version}"',
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
            time.sleep(0.3)  # 限流
        except Exception as e:
            LOG.debug(f"Maven Central 查询失败 {dep.coord}: {e}")
        return None


# ──────────────────────────────────────────────
# 迁移执行器
# ──────────────────────────────────────────────

class MigrationExecutor:
    """执行超期依赖迁移"""

    def __init__(self, project_dir, scanner):
        self.project_dir = Path(project_dir).resolve()
        self.scanner = scanner
        self.lib_expired_pom = self.project_dir / "lib-expired" / "pom.xml"
        self.repo_local_dir = self.project_dir / "repo-local"
        self.parent_pom = self.project_dir / "pom.xml"

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
        base_url = f"{MAVEN_CENTRAL_REPO}/{group_path}/{dep.artifact_id}/{dep.version}"

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

def main():
    parser = argparse.ArgumentParser(
        description="Maven 超期依赖自动迁移工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s scan    --project-dir ./demo-expired-deps
  %(prog)s migrate --project-dir ./demo-expired-deps --dry-run
  %(prog)s migrate --project-dir ./demo-expired-deps
  %(prog)s download --project-dir ./demo-expired-deps
  %(prog)s report  --project-dir ./demo-expired-deps -o report.csv
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = subparsers.add_parser("scan", help="扫描超期依赖")
    p_scan.add_argument("--project-dir", "-d", required=True, help="项目根目录")
    p_scan.add_argument("--max-age", type=int, default=DEFAULT_MAX_AGE_YEARS,
                        help=f"超期年限阈值 (默认: {DEFAULT_MAX_AGE_YEARS})")
    p_scan.add_argument("--offline", action="store_true",
                        help="离线模式（仅用本地数据库）")

    # migrate
    p_migrate = subparsers.add_parser("migrate", help="执行迁移")
    p_migrate.add_argument("--project-dir", "-d", required=True, help="项目根目录")
    p_migrate.add_argument("--max-age", type=int, default=DEFAULT_MAX_AGE_YEARS)
    p_migrate.add_argument("--dry-run", action="store_true", help="仅预览，不执行")
    p_migrate.add_argument("--offline", action="store_true")

    # download
    p_download = subparsers.add_parser("download", help="仅下载超期 jar 到本地仓库")
    p_download.add_argument("--project-dir", "-d", required=True, help="项目根目录")
    p_download.add_argument("--max-age", type=int, default=DEFAULT_MAX_AGE_YEARS)
    p_download.add_argument("--offline", action="store_true")

    # report
    p_report = subparsers.add_parser("report", help="生成报告")
    p_report.add_argument("--project-dir", "-d", required=True, help="项目根目录")
    p_report.add_argument("--max-age", type=int, default=DEFAULT_MAX_AGE_YEARS)
    p_report.add_argument("--output", "-o", default="expired_deps_report.csv")
    p_report.add_argument("--offline", action="store_true")

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
        LOG.info("📡 离线模式：仅使用本地数据库")

    # 扫描
    scanner = ProjectScanner(args.project_dir, args.max_age)
    scanner.scan()

    if args.command == "scan":
        print_scan_result(scanner)

    elif args.command == "migrate":
        print_scan_result(scanner)
        executor = MigrationExecutor(args.project_dir, scanner)
        executor.migrate(dry_run=args.dry_run)

    elif args.command == "download":
        print_scan_result(scanner)
        executor = MigrationExecutor(args.project_dir, scanner)
        for dep in scanner.expired_deps:
            if dep.version != "(inherited)":
                executor._download_to_repo_local(dep)

    elif args.command == "report":
        generate_report(scanner, args.output)
        print_scan_result(scanner)


if __name__ == "__main__":
    main()
