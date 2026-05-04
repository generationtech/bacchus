#!/bin/bash
function Completion_Stats()
{
  # Compute & output completion statistics
  #
  # Make sure these global variable have values before calling this function
  # TAR_VOLUME
  #
  # bcs_dest
  # dest_size_running
  # dest_size_running
  # source_size_running
  # source_size_total
  # start_timestamp
  # start_timestamp_running

  local avg_time
  local comp_ratio
  local completion_time
  local completion_timestamp
  local dest_size_running_text
  local source_size_total_text
  local tar_overhead
  local tar_overhead_text

  completion_timestamp=$(date +%s)
  completion_time=$(( completion_timestamp - start_timestamp - start_timestamp_running ))
  avg_time=$(( (completion_time / (TAR_VOLUME - 1) ) ))

  source_size_total_text=$(printf "%'.0f" "$source_size_total")

  tar_overhead=$(( source_size_running - source_size_total ))
  tar_overhead_text=$(printf "%'.0f" "$tar_overhead")

  dest_size_running=$(( dest_size_running + $(du -c --apparent-size "$bcs_dest" | tail -1 | awk '{ print $1 }') ))
  dest_size_running_text=$(printf "%'.0f" "$dest_size_running")

  comp_ratio=$(( 100 - ( (dest_size_running * 100) / source_size_total) ))

  printf '\nBACKUP OPERATION COMPLETE\n'
  printf 'Total runtime:                 %s\n' "$(Duration_Readable $completion_time)"
  printf 'Average time per archive file: %s\n' "$(Duration_Readable $avg_time)"
  printf 'Number of archive files:       %s\n' "$(( TAR_VOLUME - 1 ))"
  printf 'Tar overhead:                  %sk\n' "$tar_overhead_text"
  printf 'Total size of backup:          %sk\n' "$source_size_total_text"
  if [ "$dest_size_running" -ne 0 ]; then
    printf 'Total size of destinations:    %sk\n' "$dest_size_running_text"
  else
    printf 'Total size of destination:     %sk\n' "$dest_size_running_text"
  fi
  printf 'Overall compression ratio:     %s%%\n' "$comp_ratio"
}
