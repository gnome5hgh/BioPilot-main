package com.biopilot.common.mybatis.config;

import cn.dev33.satoken.stp.StpUtil;
import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor;
import com.baomidou.mybatisplus.extension.plugins.inner.TenantLineInnerInterceptor;
import java.util.List;
import net.sf.jsqlparser.expression.StringValue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 行级 user_id 统一注入：业务表 SQL 自动追加 user_id 条件（评审 P2——不手写 where）。

    走 MyBatis-Plus 租户插件改造：租户列固定 user_id。sys_* 系统表与登录日志
    不参与（用户表的主键就是 user_id 本身，语义不同）。未登录调用业务表查询
    会抛 NotLoginException——业务表只在登录态被访问，天然 fail-closed。
*/
@Configuration
public class MybatisPlusConfig {

    /** 不参与租户改写的表：系统表与登录日志（user_id 列语义不同或缺席），
        以及引擎侧跨用户读取/写入的会话与审计表。

        `bio_schedule_task` 不在豁免之列：Python 调度器走原生 SQL（不经过
        MyBatis），Java 侧查询由插件统一注入 user_id。
    */
    private static final List<String> IGNORED_TABLES = List.of(
            "sys_user", "sys_role", "sys_user_role", "sys_login_log",
            "bio_agent_state", "bio_security_audit_event");

    @Bean
    public MybatisPlusInterceptor mybatisPlusInterceptor() {
        MybatisPlusInterceptor interceptor = new MybatisPlusInterceptor();
        interceptor.addInnerInterceptor(new TenantLineInnerInterceptor(new TenantLineHandler()));
        return interceptor;
    }

    /** 供插件回调的租户判定（独立类避免 this 逃逸）。 */
    static class TenantLineHandler implements com.baomidou.mybatisplus.extension.plugins.handler.TenantLineHandler {

        @Override
        public net.sf.jsqlparser.expression.Expression getTenantId() {
            // 信任边界：登录态里的 user_id 即真相，这里不做二次鉴权。
            // 用字符串字面量注入：业务表的 user_id 是 VARCHAR，数字字面量会触发
            // MySQL 隐式转换（可能放弃索引，也可能把 '123abc' 当成 123 匹配）。
            return new StringValue(StpUtil.getLoginIdAsString());
        }

        @Override
        public String getTenantIdColumn() {
            return "user_id";
        }

        @Override
        public boolean ignoreTable(String tableName) {
            return IGNORED_TABLES.contains(tableName.toLowerCase());
        }
    }
}
