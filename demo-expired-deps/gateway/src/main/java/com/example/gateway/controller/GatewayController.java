package com.example.gateway.controller;

import com.example.common.ApiResult;
import com.example.common.CommonUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 网关路由控制器
 * 通过 common 间接使用了 guava（超期包）
 */
@RestController
@RequestMapping("/api/gateway")
public class GatewayController {

    @GetMapping("/routes")
    public ApiResult<List<String>> getRoutes() {
        List<String> routes = CommonUtils.newList(
                "/api/users -> service-user:8081",
                "/api/orders -> service-order:8082"
        );
        return ApiResult.ok(routes);
    }

    @GetMapping("/health")
    public ApiResult<String> health() {
        long freeMemory = Runtime.getRuntime().freeMemory();
        return ApiResult.ok("OK - Free memory: " + CommonUtils.readableFileSize(freeMemory));
    }
}
