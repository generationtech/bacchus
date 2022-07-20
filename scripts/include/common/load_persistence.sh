function Load_Persistence()
{
  # Make sure these global variable have values before calling this function
  # BCS_DATAFILE

  local runtime_data

  runtime_data=$(<"$BCS_DATAFILE")
  bcs_source=$(echo "$runtime_data"              | jq -r '.bcs_source')
  bcs_dest=$(echo "$runtime_data"                | jq -r '.bcs_dest')
  start_timestamp=$(echo "$runtime_data"         | jq -r '.start_timestamp')
  start_timestamp_running=$(echo "$runtime_data" | jq -r '.start_timestamp_running')
  last_timestamp=$(echo "$runtime_data"          | jq -r '.last_timestamp')
  last_timestamp_running=$(echo "$runtime_data"  | jq -r '.last_timestamp_running')
  source_size_total=$(echo "$runtime_data"       | jq -r '.source_size_total')
  source_size_running=$(echo "$runtime_data"     | jq -r '.source_size_running')
  dest_size_running=$(echo "$runtime_data"       | jq -r '.dest_size_running')
  archive_volumes=$(echo "$runtime_data"         | jq -r '.archive_volumes')
}
