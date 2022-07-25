#!/bin/bash
function Completion_Stats()
{
  # Compute & output completion statistics
  #
  # Make sure these global variable have values before calling this function
  # archive_volumes
  # dest_size_running
  # source_size_running
  # start_timestamp
  # start_timestamp_running

  local avg_time
  local comp_ratio
  local completion_time
  local completion_timestamp
  local dest_size_running_text
  local source_size_running_text

  completion_timestamp=$(date +%s)
  completion_time=$(( completion_timestamp - start_timestamp - start_timestamp_running ))
  avg_time=$(( (completion_time / archive_volumes) ))

  source_size_running_text=$(printf "%'.0f" "$source_size_running")
  dest_size_running_text=$(printf "%'.0f" "$dest_size_running")

  comp_ratio=$(( 100 - ( (source_size_running * 100) / dest_size_running) ))

  printf '\nRESTORE OPERATION COMPLETE\n'
  printf 'Total runtime:                 %s\n' "$(Duration_Readable $completion_time)"
  printf 'Average time per archive file: %s\n' "$(Duration_Readable $avg_time)"
  printf 'Number of archive files:       %s\n' "$archive_volumes"
  printf 'Total size of source:          %sk\n' "$source_size_running_text"
  printf 'Total size of restore:         %sk\n' "$dest_size_running_text"
  printf 'Overall compression ratio:     %s%%\n' "$comp_ratio"
}
