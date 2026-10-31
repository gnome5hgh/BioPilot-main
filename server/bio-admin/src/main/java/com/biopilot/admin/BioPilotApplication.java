package com.biopilot.admin;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** BioPilot 服务端启动入口（扫描 system 模块的 Mapper）。 */
@SpringBootApplication
@MapperScan("com.biopilot.system.mapper")
public class BioPilotApplication {

    public static void main(String[] args) {
        SpringApplication.run(BioPilotApplication.class, args);
    }
}
