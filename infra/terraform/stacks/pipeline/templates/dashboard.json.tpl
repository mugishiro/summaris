{
  "widgets": [
    {
      "type": "metric",
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Pipeline Executions",
        "region": "${region}",
        "metrics": [
          [ "AWS/States", "ExecutionsSucceeded", "StateMachineName", "${state_machine_name}" ],
          [ ".", "ExecutionsFailed", ".", ".", { "yAxis": "right" } ],
          [ ".", "ExecutionsTimedOut", ".", ".", { "yAxis": "right" } ]
        ],
        "stat": "Sum",
        "view": "timeSeries",
        "period": 300,
        "yAxis": {
          "left": { "label": "Succeeded" },
          "right": { "label": "Failed/Timeout" }
        }
      }
    },
    {
      "type": "metric",
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Worker Lambda Activity",
        "region": "${region}",
        "metrics": [
          [ "AWS/Lambda", "Invocations", "FunctionName", "${queue_worker_name}" ],
          [ ".", "Errors", ".", ".", { "yAxis": "right" } ]
        ],
        "stat": "Sum",
        "view": "timeSeries",
        "period": 300,
        "yAxis": {
          "left": { "label": "Invocations" },
          "right": { "label": "Errors" }
        }
      }
    },
    {
      "type": "metric",
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Polling Success Rate",
        "region": "${region}",
        "metrics": [
          [ { "expression": "100 * m1 / IF(m4>0,m4,1)", "label": "Success %", "id": "e1" } ],
          [ { "expression": "100 * (m2 + m3) / IF(m4>0,m4,1)", "label": "Failure %", "id": "e2" } ],
          [ "AWS/States", "ExecutionsSucceeded", "StateMachineName", "${state_machine_name}", { "id": "m1", "stat": "Sum", "visible": false } ],
          [ ".", "ExecutionsFailed", ".", ".", { "id": "m2", "stat": "Sum", "visible": false } ],
          [ ".", "ExecutionsTimedOut", ".", ".", { "id": "m3", "stat": "Sum", "visible": false } ],
          [ { "expression": "m1 + m2 + m3", "label": "Total", "id": "m4", "visible": false } ]
        ],
        "stat": "Average",
        "view": "timeSeries",
        "period": 300,
        "yAxis": {
          "left": { "label": "Percent", "min": 0, "max": 100 }
        }
      }
    },
    {
      "type": "metric",
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Lambda Duration (p95)",
        "region": "${region}",
        "metrics": [
          [ "AWS/Lambda", "Duration", "FunctionName", "${collector_name}", { "stat": "p95" } ],
          [ ".", ".", "FunctionName", "${preprocessor_name}", { "stat": "p95" } ],
          [ ".", ".", "FunctionName", "${summarizer_name}", { "stat": "p95" } ],
          [ ".", ".", "FunctionName", "${diff_validator_name}", { "stat": "p95" } ],
          [ ".", ".", "FunctionName", "${postprocess_name}", { "stat": "p95" } ],
          [ ".", ".", "FunctionName", "${checker_name}", { "stat": "p95" } ],
          [ ".", ".", "FunctionName", "${dispatcher_name}", { "stat": "p95" } ],
          [ ".", ".", "FunctionName", "${queue_worker_name}", { "stat": "p95" } ]
        ],
        "view": "timeSeries",
        "period": 300
      }
    },
    {
      "type": "metric",
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Lambda Errors",
        "region": "${region}",
        "metrics": [
          [ "AWS/Lambda", "Errors", "FunctionName", "${collector_name}" ],
          [ ".", ".", "FunctionName", "${preprocessor_name}" ],
          [ ".", ".", "FunctionName", "${summarizer_name}" ],
          [ ".", ".", "FunctionName", "${diff_validator_name}" ],
          [ ".", ".", "FunctionName", "${postprocess_name}" ],
          [ ".", ".", "FunctionName", "${checker_name}" ],
          [ ".", ".", "FunctionName", "${dispatcher_name}" ],
          [ ".", ".", "FunctionName", "${queue_worker_name}" ]
        ],
        "stat": "Sum",
        "view": "timeSeries",
        "period": 300
      }
    },
    {
      "type": "metric",
      "width": 12,
      "height": 6,
      "properties": {
        "title": "Raw Queue Depth",
        "region": "${region}",
        "metrics": [
          [ "AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", "${raw_queue_name}" ],
          [ ".", "ApproximateAgeOfOldestMessage", ".", ".", { "yAxis": "right" } ]
        ],
        "stat": "Average",
        "view": "timeSeries",
        "period": 300,
        "yAxis": {
          "left": { "label": "Messages" },
          "right": { "label": "Oldest Age (s)" }
        }
      }
    },
    {
      "type": "metric",
      "width": 12,
      "height": 6,
      "properties": {
        "title": "DynamoDB Latency",
        "region": "${region}",
        "metrics": [
          [ "AWS/DynamoDB", "SuccessfulRequestLatency", "TableName", "${summary_table_name}", { "stat": "p95" } ]
        ],
        "view": "timeSeries",
        "period": 300
      }
    }
  ]
}
