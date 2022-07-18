function Completion_Stats()
{
  # Compute & output completion statistics
  #
  # Make sure these global variable have values before calling this function
  # TAR_VOLUME
  # BCS_BASENAME
  #
  # start_timestamp
  # source_size_running
  # bcs_dest

  local completion_timestamp
  local diff_time
  local avg_archive_time
  local source_size_running_text
  local dest_size
  local dest_size_text
  local comp_ratio

  completion_timestamp="$(date +%s)"
  diff_time=$(( completion_timestamp - start_timestamp ))
  avg_archive_time=$(( ( diff_time / (TAR_VOLUME - 1) ) ))

  source_size_running_text=$(printf "%'.0f" "$source_size_running")

  dest_size=$(du -c "$bcs_dest"/"$BCS_BASENAME"* | tail -1 | awk '{ print $1 }')
  dest_size_text=$(printf "%'.0f" "$dest_size")

  comp_ratio=$(( 100 - ( ( dest_size * 100) / source_size_running ) ))

  printf '\nBACKUP OPERATION COMPLETE\n'
  printf 'Total runtime:                 %s\n' "$( Duration_Readable $diff_time )"
  printf 'Average time per archive file: %s\n' "$( Duration_Readable $avg_archive_time )"
  printf 'Number of archive files:       %s\n' "$(( TAR_VOLUME - 1 ))"
  printf 'Total space backed up:         %sk\n' "$source_size_running_text"
  printf 'Total space on destination:    %sk\n' "$dest_size_text"
  printf 'Overall compression ratio:     %s%%\n' "$comp_ratio"
}