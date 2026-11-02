package com.biopilot.schedule.service;

/** 定时任务调度：到期扫描、认领与投递（投递即调引擎内部端点）。 */
public interface ScheduleDispatchService {

    /** 每分钟扫一次到期任务；单线程串行，避免同一实例内重叠。 */
    void scheduledDispatch();

    /**
     * 扫描一轮到期任务并投递。
     *
     * Returns:
     *     成功投递给引擎的任务数。
     */
    int dispatchOnce();
}
