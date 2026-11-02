package com.biopilot.schedule.service.impl;

import com.biopilot.schedule.service.ScheduleService;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.schedule.domain.BioScheduleTask;
import com.biopilot.schedule.dto.ScheduleView;
import com.biopilot.schedule.mapper.BioScheduleTaskMapper;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;

/** 定时任务定义维护：任务行与调度进度全部由 Java 写。

    到期扫描与认领在 {@code ScheduleDispatchService}，执行只调引擎内部端点跑一遍
    agent；引擎不再直接读写 `bio_schedule_task`。
*/
@Service
public class ScheduleServiceImpl implements ScheduleService {

    /** 与引擎侧 datetime.isoformat() 同形：带微秒与 +00:00 偏移，字符串比较即可排序。 */
    private static final DateTimeFormatter TS =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSSSSxxx");

    private final BioScheduleTaskMapper mapper;

    public ScheduleServiceImpl(BioScheduleTaskMapper mapper) {
        this.mapper = mapper;
    }

    public List<ScheduleView> list() {
        return mapper.selectList(new LambdaQueryWrapper<BioScheduleTask>()
                        .orderByDesc(BioScheduleTask::getCreatedAt))
                .stream().map(ScheduleView::from).toList();
    }

    /** 新建任务：下一次执行时间按周期从当前时刻起算。 */
    public Map<String, Object> create(String userId, Map<String, Object> body) {
        String name = text(body.get("name"));
        String task = text(body.get("task"));
        String conversationId = text(body.get("conversation_id"));
        int interval = parseInt(body.get("interval_minutes"));
        if (name.isEmpty() || task.isEmpty() || conversationId.isEmpty() || interval < 5) {
            throw new ServiceException(422,
                    "name/task/conversation_id 必填，interval_minutes ≥ 5");
        }
        OffsetDateTime now = OffsetDateTime.now(ZoneOffset.UTC);
        BioScheduleTask row = new BioScheduleTask();
        row.setId(UUID.randomUUID().toString().replace("-", ""));
        row.setUserId(userId);
        row.setConversationId(conversationId);
        row.setName(name.length() > 200 ? name.substring(0, 200) : name);
        row.setTask(task);
        row.setIntervalMinutes(interval);
        row.setPaused(0);
        row.setNextRunAt(now.plusMinutes(interval).format(TS));
        row.setCreatedAt(now.format(TS));
        mapper.insert(row);
        return Map.of("status", "ok");
    }

    /** 暂停/恢复：不动已排队的 next_run_at，恢复后照常到期执行。 */
    public Map<String, Object> setPaused(String taskId, int paused) {
        mapper.update(null, new LambdaUpdateWrapper<BioScheduleTask>()
                .eq(BioScheduleTask::getId, taskId)
                .set(BioScheduleTask::getPaused, paused));
        return Map.of("status", "ok");
    }

    /** 立即执行：把 next_run_at 提前到当前时刻，由调度器在下一轮（≤60 秒）取走。 */
    public Map<String, Object> runNow(String taskId) {
        BioScheduleTask row = mapper.selectById(taskId);
        if (row == null) {
            throw new ServiceException(404, "定时任务不存在");
        }
        mapper.update(null, new LambdaUpdateWrapper<BioScheduleTask>()
                .eq(BioScheduleTask::getId, taskId)
                .set(BioScheduleTask::getNextRunAt,
                        OffsetDateTime.now(ZoneOffset.UTC).format(TS)));
        return Map.of("status", "queued");
    }

    public Map<String, Object> delete(String taskId) {
        mapper.deleteById(taskId);
        return Map.of("status", "ok");
    }

    private String text(Object value) {
        return value == null ? "" : String.valueOf(value).trim();
    }

    private int parseInt(Object value) {
        try {
            return Integer.parseInt(text(value));
        } catch (NumberFormatException e) {
            return 0;
        }
    }
}
