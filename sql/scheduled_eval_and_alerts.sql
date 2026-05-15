-- =============================================================================
-- Scheduled Evaluation Task
-- Runs evaluation at a defined cadence to detect regressions from external
-- factors (model updates, data changes, tool drift)
-- =============================================================================

-- Pin orchestration LLM to ensure reproducible results
-- ALTER AGENT MARKETING_CAMPAIGNS_DB.AGENTS.MARKETING_CAMPAIGNS_AGENT
--   SET SPEC = $$ ... "models": {"orchestration": "claude-4-sonnet"} ... $$;

CREATE OR REPLACE TASK MARKETING_CAMPAIGNS_DB.AGENTS.AGENT_SCHEDULED_EVAL_TASK
  WAREHOUSE = COMPUTE_WH
  SCHEDULE = 'USING CRON 0 6 * * * America/Los_Angeles'  -- Daily at 6 AM PT
AS
CALL EXECUTE_AI_EVALUATION(
  'START',
  OBJECT_CONSTRUCT(
    'run_name', 'scheduled_eval_' || TO_CHAR(CURRENT_TIMESTAMP(), 'YYYYMMDD_HH24MISS') || '_' || LEFT(UUID_STRING(), 8)
  ),
  '@MARKETING_CAMPAIGNS_DB.AGENTS.EVAL_CONFIG_STAGE/eval_config.yaml'
);

-- Enable the task
ALTER TASK MARKETING_CAMPAIGNS_DB.AGENTS.AGENT_SCHEDULED_EVAL_TASK RESUME;

-- Verify task is running
SHOW TASKS LIKE 'AGENT_SCHEDULED_EVAL_TASK' IN SCHEMA MARKETING_CAMPAIGNS_DB.AGENTS;


-- =============================================================================
-- Notification Integration (one-time setup)
-- =============================================================================

CREATE OR REPLACE NOTIFICATION INTEGRATION agent_eval_email_int
  TYPE = EMAIL
  ENABLED = TRUE
  ALLOWED_RECIPIENTS = ('admin@example.com');  -- Replace with your email


-- =============================================================================
-- Alert 1: Evaluation Accuracy Threshold
-- Fires when answer_correctness drops below 70%
-- =============================================================================

CREATE OR REPLACE ALERT MARKETING_CAMPAIGNS_DB.AGENTS.AGENT_EVAL_ACCURACY_ALERT
  WAREHOUSE = COMPUTE_WH
  SCHEDULE = '1 HOUR'
  IF (EXISTS (
    SELECT *
    FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
      'MARKETING_CAMPAIGNS_DB',
      'AGENTS',
      'MARKETING_CAMPAIGNS_AGENT',
      'CORTEX AGENT',
      (SELECT MAX(RUN_NAME) FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
        'MARKETING_CAMPAIGNS_DB', 'AGENTS', 'MARKETING_CAMPAIGNS_AGENT', 'CORTEX AGENT', NULL
      )))
    ))
    WHERE METRIC_NAME = 'answer_correctness'
    AND EVAL_AGG_SCORE < 0.7
  ))
  THEN
    CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(
      SNOWFLAKE.NOTIFICATION.TEXT_PLAIN(
        'ALERT: Marketing Campaigns Agent evaluation accuracy dropped below 70% threshold. Check latest evaluation run in Snowsight.'
      ),
      '{"agent_eval_email_int": {"toAddress": ["admin@example.com"]}}'
    );

ALTER ALERT MARKETING_CAMPAIGNS_DB.AGENTS.AGENT_EVAL_ACCURACY_ALERT RESUME;


-- =============================================================================
-- Alert 2: Agent Latency Threshold
-- Fires when agent response time exceeds 5 seconds
-- =============================================================================

CREATE OR REPLACE ALERT MARKETING_CAMPAIGNS_DB.AGENTS.AGENT_LATENCY_ALERT
  WAREHOUSE = COMPUTE_WH
  SCHEDULE = '1 HOUR'
  IF (EXISTS (
    SELECT *
    FROM MARKETING_CAMPAIGNS_DB.AGENTS.AGENT_EVENT_TABLE  -- Replace with your event table
    WHERE TIMESTAMP > DATEADD('HOUR', -1, CURRENT_TIMESTAMP())
      AND RESOURCE_ATTRIBUTES['snow.executable.type'] = 'AGENT'
      AND RECORD_TYPE = 'SPAN'
      AND RECORD['status']['code'] = 'STATUS_CODE_OK'
      AND TIMESTAMPDIFF('MILLISECOND',
            TIMESTAMP,
            RECORD['end_time']::TIMESTAMP_NTZ
          ) > 5000
  ))
  THEN
    CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(
      SNOWFLAKE.NOTIFICATION.TEXT_PLAIN(
        'ALERT: Marketing Campaigns Agent latency exceeded 5s threshold in the last hour.'
      ),
      '{"agent_eval_email_int": {"toAddress": ["admin@example.com"]}}'
    );

ALTER ALERT MARKETING_CAMPAIGNS_DB.AGENTS.AGENT_LATENCY_ALERT RESUME;


-- =============================================================================
-- Alert 3: Agent Reliability
-- Fires when error rate exceeds 5%
-- =============================================================================

CREATE OR REPLACE ALERT MARKETING_CAMPAIGNS_DB.AGENTS.AGENT_RELIABILITY_ALERT
  WAREHOUSE = COMPUTE_WH
  SCHEDULE = '1 HOUR'
  IF (EXISTS (
    SELECT *
    FROM (
      SELECT
        COUNT_IF(RECORD['status']['code'] = 'STATUS_CODE_ERROR') AS error_count,
        COUNT(*) AS total_count,
        ROUND(1 - (error_count / NULLIF(total_count, 0)), 4) AS reliability_score
      FROM MARKETING_CAMPAIGNS_DB.AGENTS.AGENT_EVENT_TABLE  -- Replace with your event table
      WHERE TIMESTAMP > DATEADD('HOUR', -1, CURRENT_TIMESTAMP())
        AND RESOURCE_ATTRIBUTES['snow.executable.type'] = 'AGENT'
        AND RECORD_TYPE = 'SPAN'
    )
    WHERE reliability_score < 0.95
  ))
  THEN
    CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(
      SNOWFLAKE.NOTIFICATION.TEXT_PLAIN(
        'ALERT: Marketing Campaigns Agent reliability dropped below 95% in the last hour.'
      ),
      '{"agent_eval_email_int": {"toAddress": ["admin@example.com"]}}'
    );

ALTER ALERT MARKETING_CAMPAIGNS_DB.AGENTS.AGENT_RELIABILITY_ALERT RESUME;


-- =============================================================================
-- Alert 4: User Feedback Satisfaction
-- Fires when positive feedback drops below 80%
-- =============================================================================

CREATE OR REPLACE ALERT MARKETING_CAMPAIGNS_DB.AGENTS.AGENT_FEEDBACK_ALERT
  WAREHOUSE = COMPUTE_WH
  SCHEDULE = '1 HOUR'
  IF (EXISTS (
    SELECT *
    FROM (
      SELECT
        COUNT_IF(FEEDBACK = 'negative') AS negative_count,
        COUNT_IF(FEEDBACK = 'positive') AS positive_count,
        COUNT(*) AS total_count,
        ROUND(positive_count / NULLIF(total_count, 0), 4) AS satisfaction_score
      FROM MARKETING_CAMPAIGNS_DB.AGENTS.AGENT_EVENT_TABLE  -- Replace with your event table
      WHERE TIMESTAMP > DATEADD('HOUR', -24, CURRENT_TIMESTAMP())
        AND RESOURCE_ATTRIBUTES['snow.executable.type'] = 'AGENT'
        AND RECORD_TYPE = 'SPAN'
        AND RECORD['name'] = 'user_feedback'
    )
    WHERE satisfaction_score < 0.80
      AND total_count >= 5
  ))
  THEN
    CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(
      SNOWFLAKE.NOTIFICATION.TEXT_PLAIN(
        'ALERT: Marketing Campaigns Agent user satisfaction dropped below 80% in the last 24 hours.'
      ),
      '{"agent_eval_email_int": {"toAddress": ["admin@example.com"]}}'
    );

ALTER ALERT MARKETING_CAMPAIGNS_DB.AGENTS.AGENT_FEEDBACK_ALERT RESUME;
