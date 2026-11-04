package com.biopilot.file.service;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** OSS 删除队列与孤儿对账的定时入口。 */
@Component
public class OssGcJob {

    private final OssGcService gc;

    public OssGcJob(OssGcService gc) {
        this.gc = gc;
    }

    /** 每分钟处理到期的删除任务。 */
    @Scheduled(fixedDelay = 60_000, initialDelay = 30_000)
    public void runDue() {
        gc.runDue();
    }

    /** 每 6 小时做一轮前缀对账（启动 10 分钟后先跑一次）。 */
    @Scheduled(fixedDelay = 21_600_000, initialDelay = 600_000)
    public void reconcile() {
        gc.reconcileAll();
    }
}
