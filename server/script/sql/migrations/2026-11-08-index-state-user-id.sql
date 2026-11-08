-- local 域退役 + bio_rag_index_state 隔离键改名：项目已只服务多用户平台，
-- 引擎不再有无用户的运行形态（单机/评测脚本必须显式传真实 user_id）。
-- 执行前提：先停引擎与 server。local 行是评测/单机时代的索引账本，可丢。
USE biopilot;

DELETE FROM bio_rag_index_state WHERE user_domain='local';
ALTER TABLE bio_rag_index_state RENAME COLUMN user_domain TO user_id;

-- 追补：随「无用户形态退役」，存量表的 user_id 列默认值一并移除
-- （新写入必须显式携带归属；历史行不动）。
ALTER TABLE bio_message ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE bio_memory_block ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE bio_memory_block_history ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE bio_agent_state ALTER COLUMN user_id DROP DEFAULT;

-- 测试库的 bio_message 建表早于多用户改造且增量补列从未落到它（0 行，直接补列）。
ALTER TABLE biopilot_test.bio_message
    ADD COLUMN user_id VARCHAR(191) NOT NULL AFTER agent_id;
