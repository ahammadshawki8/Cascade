-- ============================================================================
-- 005_step_detail.sql — keep what each run actually did
-- ============================================================================
-- `episodes` recorded how many steps a run took and what it cost, but not the
-- calls themselves. So the run history could say which gate decided a run and
-- never what the agent did inside it: every past run collapsed to a verdict
-- plus a step count.
--
-- The trajectory is bounded by max_steps_per_task, so this is a small object,
-- not a log. S3 stays the archive when a bucket is configured; this column is
-- what makes the detail readable without a bucket round trip, which is the
-- only mode local development and the demo ever run in.
--
-- Additive and nullable on purpose: the writer treats it as best effort, so a
-- database that has not taken this migration still records episodes normally.

ALTER TABLE episodes ADD COLUMN IF NOT EXISTS trajectory JSONB;
