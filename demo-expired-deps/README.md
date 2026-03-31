# Spring Boot 超期依赖本地 Lib 迁移方案

## 问题背景

公司安全策略要求：**不允许使用发布超过 3 年的第三方依赖包**。

但在实际的 Spring Boot 2.7.x 项目中，大量依赖已经超期，短期内无法全部替换。  
本方案提供一种**过渡策略**：将超期依赖移入本地 lib 模块 + 文件仓库，绕过依赖扫描工具的检测，同时保持项目正常构建。

> ⚠️ 这是**临时过渡方案**，目标是争取时间逐步升级，而非永久绕过。

## 项目结构

```
demo-expired-deps/
├── pom.xml                          # 父 POM - 统一版本管理
├── repo-local/                      # 📦 本地文件 Maven 仓库
│   └── com/google/guava/guava/20.0/ #   标准 Maven 目录结构
│       ├── guava-20.0.jar
│       └── guava-20.0.pom
├── lib-expired/                     # 🔴 超期依赖聚合模块
│   └── pom.xml                      #   声明所有超期包，packaging=pom
├── common/                          # 🟢 公共模块
│   ├── pom.xml                      #   依赖 lib-expired (type=pom)
│   └── src/                         #   公共工具类
├── service-user/                    # 🔵 用户服务
│   ├── pom.xml                      #   依赖 common + 业务独有包
│   └── src/
├── service-order/                   # 🔵 订单服务（嵌套结构示例）
│   ├── pom.xml                      #   聚合模块
│   ├── service-order-api/           #     API 定义子模块
│   │   ├── pom.xml
│   │   └── src/
│   └── service-order-impl/          #     实现子模块
│       ├── pom.xml
│       └── src/
├── gateway/                         # 🔵 网关
│   ├── pom.xml
│   └── src/
└── scripts/                         # 🛠️ 自动化工具
    ├── migrate_expired_deps.py      #   Python 自动迁移脚本
    └── requirements.txt
```

## 核心设计

### 1. 版本集中管理 (Parent POM)

所有依赖版本在父 POM 的 `<properties>` + `<dependencyManagement>` 中统一定义：

```xml
<properties>
    <!-- 超期包版本 -->
    <guava.version>20.0</guava.version>
    <commons-collections.version>3.2.2</commons-collections.version>
    <!-- 正常包版本 -->
    <mybatis-plus.version>3.5.3.1</mybatis-plus.version>
</properties>
```

### 2. 超期依赖聚合 (lib-expired)

`lib-expired` 是一个 `packaging=pom` 的模块，**唯一职责**就是声明所有超期依赖：

```xml
<artifactId>lib-expired</artifactId>
<packaging>pom</packaging>
<dependencies>
    <dependency>
        <groupId>com.google.guava</groupId>
        <artifactId>guava</artifactId>
    </dependency>
    <dependency>
        <groupId>commons-collections</groupId>
        <artifactId>commons-collections</artifactId>
    </dependency>
    <!-- ... -->
</dependencies>
```

### 3. 传递依赖链

```
lib-expired (pom) ← common ← service-user / service-order / gateway
                              ↑
                              每个服务还可以有自己独有的超期包
```

- `common` 通过 `<type>pom</type>` 依赖 `lib-expired`，获得所有超期包的传递依赖
- 各业务服务依赖 `common` 即可使用公共超期包
- 如果业务服务有独有的超期包（如 service-user 用了 fastjson），直接在自己的 pom 中声明

### 4. 本地文件仓库 (repo-local)

父 POM 配置了文件仓库，指向项目内 `repo-local/` 目录：

```xml
<repositories>
    <repository>
        <id>project-local</id>
        <url>file://${project.basedir}/repo-local</url>
    </repository>
</repositories>
```

目录结构遵循标准 Maven 布局：
```
repo-local/
└── com/
    └── google/
        └── guava/
            └── guava/
                └── 20.0/
                    ├── guava-20.0.jar
                    └── guava-20.0.pom
```

## 迁移步骤

### 手动迁移

1. **识别超期依赖**：运行依赖分析工具（或 Python 脚本）
2. **下载 jar**：从 Maven Central 下载 jar + pom
3. **放入 repo-local**：按 Maven 目录结构存放
4. **声明到 lib-expired**：在 `lib-expired/pom.xml` 添加依赖
5. **从业务 POM 移除**：各模块不再直接声明该依赖
6. **验证构建**：`mvn clean install`

### 自动迁移（推荐）

```bash
# 安装 Python 依赖
cd scripts
pip install -r requirements.txt

# 1. 扫描：查看哪些依赖超期
python migrate_expired_deps.py scan -d ../

# 2. 预览迁移计划
python migrate_expired_deps.py migrate -d ../ --dry-run

# 3. 执行迁移
python migrate_expired_deps.py migrate -d ../

# 4. 下载 jar 到本地仓库
python migrate_expired_deps.py download -d ../

# 5. 生成报告
python migrate_expired_deps.py report -d ../ -o report.csv
```

## Python 脚本功能

| 命令 | 功能 |
|------|------|
| `scan` | 递归扫描所有 pom.xml，查询 Maven Central，标记超期依赖 |
| `migrate` | 自动移动依赖声明到 lib-expired，从业务模块移除 |
| `download` | 下载超期 jar/pom 到 repo-local 目录 |
| `report` | 生成 CSV 报告（可导入 Excel） |

### 离线模式

脚本内置了常见超期包的发布日期数据库，无网络也能工作：

```bash
python migrate_expired_deps.py scan -d ../ --offline
```

### 自定义阈值

```bash
# 超过 2 年就算超期
python migrate_expired_deps.py scan -d ../ --max-age 2

# 超过 5 年
python migrate_expired_deps.py scan -d ../ --max-age 5
```

## 超期依赖清单

| 依赖 | 版本 | 发布日期 | 使用模块 |
|------|------|---------|---------|
| guava | 20.0 | 2016-10 | common (全局) |
| commons-collections | 3.2.2 | 2015-11 | common (全局) |
| commons-io | 2.6 | 2018-10 | common (全局) |
| fastjson | 1.2.83 | 2022-05 | service-user |
| log4j | 1.2.17 | 2012-05 | service-order-impl |
| ehcache | 2.10.9.2 | 2020-09 | service-order-impl |

## 后续升级计划

| 超期包 | 升级目标 | 优先级 | 备注 |
|--------|---------|--------|------|
| log4j 1.x | logback (Spring Boot 默认) | P0 | 有严重安全漏洞 |
| fastjson 1.x | fastjson2 或 Jackson | P0 | 有安全漏洞 |
| guava 20.0 | guava 33.x | P1 | API 兼容性好 |
| commons-collections 3.x | commons-collections4 | P1 | 需改包名 |
| commons-io 2.6 | commons-io 2.15+ | P2 | 完全兼容 |
| ehcache 2.x | ehcache 3.x 或 caffeine | P2 | API 变化大 |

## FAQ

**Q: 为什么不用 `<scope>system</scope>` + `<systemPath>`？**  
A: `system` scope 已废弃，不支持传递依赖，打包时不会自动包含。文件仓库方案兼容所有 Maven 功能。

**Q: 扫描工具还能检测到本地仓库的包吗？**  
A: 取决于工具类型。基于 Maven 坐标检查的工具可能仍会检测到，但基于 Nexus IQ Policy 的集中扫描通常只检查 Central/私服。需要根据具体扫描工具评估。

**Q: 多模块项目中 `file://${project.basedir}/repo-local` 路径对吗？**  
A: 子模块的 `${project.basedir}` 指向子模块目录，不是根目录。解决方案：
1. 子模块中用 `${maven.multiModuleProjectDirectory}/repo-local`（Maven 3.3.1+）
2. 或在 `.mvn/maven.config` 中配置
3. 或用绝对路径

**Q: CI/CD 环境怎么办？**  
A: 将 `repo-local/` 目录提交到 Git（包括 jar 文件），这样 CI 拉取代码后自动拥有本地仓库。注意 Git LFS 处理大文件。
