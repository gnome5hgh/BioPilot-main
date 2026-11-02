package com.biopilot.schedule.service.impl;

import com.biopilot.schedule.service.ScheduleDispatchService;

import com.biopilot.common.web.http.AgentInternalClient;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

/**
 * 定时任务调度：到期扫描、认领与投递。
 *
 * <p>任务定义与进度列都归 Java；引擎只负责收到触发后跑一遍 agent。扫描跨用户，
 * 因此走 JdbcTemplate 绕过租户插件（没有登录态时租户插件会抛 NotLoginException），
 * 这是本模块唯一的系统级查询。</p>
 *
 * <p>认领用「旧 next_run_at」做 CAS：多实例同时扫到同一行时只有一个更新成功，
 * 避免重复投递。投递失败也保留已推进的时间——与旧行为一致，防止失败任务每轮
 * 重试刷爆。</p>
 */
@Service
public class ScheduleDispatchServiceImpl implements ScheduleDispatchService {

    private static final Logger log = LoggerFactory.getLogger(ScheduleDispatchService.class);

    /** 与 ScheduleService / 旧引擎同形：固定宽度，字符串比较即可排序。 */
    private static final DateTimeFormatter TS =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSSSSxxx");

    private final JdbcTemplate jdbc;
    private final AgentInternalClient internal;

    public ScheduleDispatchServiceImpl(JdbcTemplate jdbc, AgentInternalClient internal) {
        this.jdbc = jdbc;
        this.internal = internal;
    }

    /** 每分钟扫一次到期任务；单线程串行，避免同一实例内重叠。 */
    @Scheduled(fixedDelay = 60_000, initialDelay = 30_000)
    public void scheduledDispatch() {
        try {
            int count = dispatchOnce();
            if (count > 0) {
                log.info("定时任务投递 {} 条", count);
            }
        } catch (RuntimeException e) {
            log.warn("定时任务扫描失败", e);
        }
    }

    /**
     * 扫描一轮到期任务并投递，返回实际投递条数。
     *
     * @return 成功投递给引擎的任务数。
     */
    public int dispatchOnce() {
        String now = OffsetDateTime.now(ZoneOffset.UTC).format(TS);
        List<Map<String, Object>> due = jdbc.queryForList(
                "SELECT id, user_id, conversation_id, name, task, interval_minutes, next_run_at"
                        + " FROM bio_schedule_task"
                        + " WHERE paused=0 AND next_run_at<=?"
                        + " ORDER BY next_run_at LIMIT 50",
                now);
        int dispatched = 0;
        for (Map<String, Object> row : due) {
            String id = text(row.get("id"));
            String oldNext = text(row.get("next_run_at"));
            int interval = intValue(row.get("interval_minutes"));
            String next = OffsetDateTime.now(ZoneOffset.UTC)
                    .plusMinutes(Math.max(1, interval)).format(TS);
            int claimed = jdbc.update(
                    "UPDATE bio_schedule_task SET last_run_at=?, next_run_at=?"
                            + " WHERE id=? AND next_run_at=? AND paused=0",
                    now, next, id, oldNext);
            if (claimed == 0) {
                continue;
            }
            long userId;
            try {
                userId = Long.parseLong(text(row.get("user_id")));
            } catch (NumberFormatException e) {
                log.warn("定时任务 user_id 非数字，跳过投递 id={} user={}",
                        id, row.get("user_id"));
                continue;
            }
            internal.runSchedule(userId, id, text(row.get("conversation_id")),
                    text(row.get("task")), text(row.get("name")));
            dispatched += 1;
        }
        return dispatched;
    }

    private static String text(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private static int intValue(Object value) {
        try {
            return Integer.parseInt(text(value));
        } catch (NumberFormatException e) {
            return 0;
        }
    }
}
