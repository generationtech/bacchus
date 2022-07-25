#!/bin/bash
function Load_Persistence()
{
  # Make sure these global variable have values before calling this function
  # BCS_DATAFILE

  local runtime_data

  runtime_data=$(<"$BCS_DATAFILE")
  archive_volumes=$(echo "$runtime_data"               | jq -r '.archive_volumes')
  bcs_source=$(echo "$runtime_data"                    | jq -r '.bcs_source')
  bcs_dest=$(echo "$runtime_data"                      | jq -r '.bcs_dest')
  start_timestamp=$(echo "$runtime_data"               | jq -r '.start_timestamp')
  start_timestamp_running=$(echo "$runtime_data"       | jq -r '.start_timestamp_running')
  incremental_timestamp=$(echo "$runtime_data"         | jq -r '.incremental_timestamp')
  incremental_timestamp_running=$(echo "$runtime_data" | jq -r '.incremental_timestamp_running')
  remain_text_size_running=$(echo "$runtime_data"      | jq -r '.remain_text_size_running')
  incremental_text_size_running=$(echo "$runtime_data" | jq -r '.incremental_text_size_running')
  avg_text_size_running=$(echo "$runtime_data"         | jq -r '.avg_text_size_running')
  comp_ratio_text_size_running=$(echo "$runtime_data"  | jq -r '.comp_ratio_text_size_running')
  source_size_total=$(echo "$runtime_data"             | jq -r '.source_size_total')
  source_size_running=$(echo "$runtime_data"           | jq -r '.source_size_running')
  dest_size_running=$(echo "$runtime_data"             | jq -r '.dest_size_running')
  size_text_running=$(echo "$runtime_data"             | jq -r '.size_text_running')
}
