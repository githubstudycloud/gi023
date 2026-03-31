package com.example.order.impl.controller;

import com.example.common.ApiResult;
import com.example.common.CommonUtils;
import com.example.order.api.OrderDTO;
import com.example.order.api.OrderService;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;
import java.util.List;

/**
 * 订单控制器
 * 
 * 用了 common 传递的 guava（超期）+ 本模块的 ehcache（超期）
 */
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping
    public ApiResult<List<String>> listOrders() {
        List<String> orders = CommonUtils.newList("ORD-001", "ORD-002");
        return ApiResult.ok(orders);
    }

    @GetMapping("/{id}")
    public ApiResult<OrderDTO> getOrder(@PathVariable Long id) {
        OrderDTO dto = new OrderDTO();
        dto.setId(id);
        dto.setOrderNo("ORD-" + id);
        dto.setAmount(BigDecimal.valueOf(99.99));
        dto.setStatus("PAID");
        return ApiResult.ok(dto);
    }
}
