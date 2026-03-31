package com.example.order.api;

/**
 * 订单服务接口（供外部调用方依赖）
 */
public interface OrderService {

    OrderDTO getOrderById(Long id);

    OrderDTO createOrder(Long userId, String productId);
}
