package com.biopilot.schedule.service;

import com.biopilot.schedule.dto.ScheduleView;
import java.util.List;
import java.util.Map;

/** 定时任务定义维护：任务行与调度进度全部由 Java 写。 */
public interface ScheduleService {

    /** 本用户的任务清单（新→旧）。 */
    List<ScheduleView> list();

    /** 新建任务：下一次执行时间按周期从当前时刻起算。 */
    Map<String, Object> create(String userId, Map<String, Object> body);

    /** 暂停/恢复：不动已排队的 next_run_at。 */
    Map<String, Object> setPaused(String taskId, int paused);

    /** 立即执行：把 next_run_at 提前到当前时刻，由调度器取走。 */
    Map<String, Object> runNow(String taskId);

    /** 删除任务。 */
    Map<String, Object> delete(String taskId);
}
