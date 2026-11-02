package com.biopilot.admin;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** BioPilot 服务端启动入口（扫描各业务域的 Mapper）。 */
@SpringBootApplication(scanBasePackages = "com.biopilot")
@MapperScan({"com.biopilot.system.mapper", "com.biopilot.project.mapper",
        "com.biopilot.catalog.mapper", "com.biopilot.schedule.mapper"})
public class BioPilotApplication {

    public static void main(String[] args) {
        SpringApplication.run(BioPilotApplication.class, args);
    }
}
