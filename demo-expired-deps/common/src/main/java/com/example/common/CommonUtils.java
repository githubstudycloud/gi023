package com.example.common;

import com.google.common.collect.Lists;
import org.apache.commons.collections.CollectionUtils;
import org.apache.commons.io.FileUtils;

import java.util.List;

/**
 * 公共工具类 - 演示超期依赖的使用
 * 
 * 这里用了 guava、commons-collections、commons-io
 * 这三个都是超期包，实际 jar 来自 repo-local/ 本地仓库
 */
public class CommonUtils {

    /**
     * 使用 guava 创建列表
     */
    public static <T> List<T> newList(T... items) {
        return Lists.newArrayList(items);
    }

    /**
     * 使用 commons-collections 判断集合非空
     */
    public static boolean isNotEmpty(java.util.Collection<?> coll) {
        return CollectionUtils.isNotEmpty(coll);
    }

    /**
     * 使用 commons-io 获取文件大小的可读格式
     */
    public static String readableFileSize(long size) {
        return FileUtils.byteCountToDisplaySize(size);
    }
}
