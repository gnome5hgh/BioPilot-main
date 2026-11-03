package com.biopilot.admin;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

/** BioPilot 服务端启动入口（扫描各业务域的 Mapper）。 */
@EnableScheduling
@SpringBootApplication(scanBasePackages = "com.biopilot")
@MapperScan({"com.biopilot.system.mapper", "com.biopilot.project.mapper",
        "com.biopilot.file.mapper", "com.biopilot.schedule.mapper",
        "com.biopilot.citation.mapper", "com.biopilot.literature.mapper",
        "com.biopilot.skill.mapper"})
public class BioPilotApplication {

    public static void main(String[] args) {
        SpringApplication.run(BioPilotApplication.class, args);
    }
}
