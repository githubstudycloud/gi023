# repo-local - 本地 Maven 仓库

此目录是一个 file-based 的 Maven 仓库，用于存放超期依赖的 jar 文件。

## 目录结构

标准 Maven 仓库目录格式：

```
repo-local/
├── com/
│   ├── google/
│   │   └── guava/
│   │       └── guava/
│   │           └── 20.0/
│   │               ├── guava-20.0.jar
│   │               └── guava-20.0.pom
│   └── alibaba/
│       └── fastjson/
│           └── 1.2.83/
│               ├── fastjson-1.2.83.jar
│               └── fastjson-1.2.83.pom
├── commons-collections/
│   └── commons-collections/
│       └── 3.2.2/
│           ├── commons-collections-3.2.2.jar
│           └── commons-collections-3.2.2.pom
└── ...
```

## 使用方式

1. 运行 `python scripts/migrate_expired_deps.py migrate` 自动填充此目录
2. 或手动将 jar/pom 放入对应路径
3. 父 POM 中已配置本目录为 `<repository>`

## 注意

- 此目录应提交到 Git（jar 文件是项目构建的一部分）
- 如果 jar 文件过大，考虑使用 Git LFS
- 后续升级时，删除对应目录并更新父 POM 版本号即可
