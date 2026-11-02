package com.biopilot.schedule.dto;

import com.biopilot.schedule.domain.BioScheduleTask;
import com.fasterxml.jackson.annotation.JsonProperty;

/** 定时任务列表项：字段名与前端既有契约一致（interval_minutes / next_run_at）。 */
public record ScheduleView(
        String id,
        @JsonProperty("conversation_id") String conversationId,
        String name,
        String task,
        @JsonProperty("interval_minutes") int intervalMinutes,
        int paused,
        @JsonProperty("last_run_at") String lastRunAt,
        @JsonProperty("next_run_at") String nextRunAt) {

    public static ScheduleView from(BioScheduleTask row) {
        return new ScheduleView(
                row.getId(),
                row.getConversationId(),
                row.getName(),
                row.getTask(),
                row.getIntervalMinutes() == null ? 0 : row.getIntervalMinutes(),
                row.getPaused() == null ? 0 : row.getPaused(),
                row.getLastRunAt(),
                row.getNextRunAt());
    }
}
