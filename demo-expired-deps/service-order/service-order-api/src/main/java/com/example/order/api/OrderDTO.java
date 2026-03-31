package com.example.order.api;

import lombok.Data;

import java.io.Serializable;
import java.math.BigDecimal;

/**
 * 订单 DTO - 跨服务传输对象
 */
@Data
public class OrderDTO implements Serializable {

    private Long id;
    private Long userId;
    private String orderNo;
    private BigDecimal amount;
    private String status;
}
