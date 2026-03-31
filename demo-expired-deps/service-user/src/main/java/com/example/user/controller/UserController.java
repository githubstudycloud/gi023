package com.example.user.controller;

import com.alibaba.fastjson.JSON;
import com.example.common.ApiResult;
import com.example.common.CommonUtils;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 用户控制器 - 演示超期依赖的使用场景
 * 
 * 用了 fastjson（超期）和 common 里的 guava（超期）
 */
@RestController
@RequestMapping("/api/users")
public class UserController {

    @GetMapping
    public ApiResult<List<String>> listUsers() {
        // 使用 guava（通过 common 传递的超期包）
        List<String> users = CommonUtils.newList("Alice", "Bob", "Charlie");
        return ApiResult.ok(users);
    }

    @PostMapping
    public ApiResult<String> createUser(@RequestBody String body) {
        // 使用 fastjson（本模块独有的超期包）
        Object parsed = JSON.parse(body);
        return ApiResult.ok("User created: " + parsed);
    }
}
