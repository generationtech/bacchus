function Incremental_Stats()
{
  # Compute & output incremntal statistics
  #
  # Make sure these global variable have values before calling this function
  # BCS_BASENAME
  # TAR_VOLUME
  #
  # archive_volumes
  # source_size_total
  # source_size_running
  # start_timestamp
  # last_time
  # bcs_dest

  local archive_max_name
  local archive_max_num
  local source_size_text
  local max_source_size_text
  local source_size_running_text
  local completion_timestamp
  local diff_time
  local avg_archive_time
  local remain_time
  local last_time
  local dest_size
  local comp_ratio
  local dest_size_text

  archive_max_name=$(( ${#BCS_BASENAME} + ${#archive_volumes} + 5 ))
  archive_max_num=$(( ${#archive_volumes} + 1 ))

  source_size_text=${#source_size_total}
  max_source_size_text=$(( source_size_text + (source_size_text / 3) + 9 ))
  source_size_running_text=$(printf "%'.0f" "$source_size_running")

  completion_timestamp="$(date +%s)"
  diff_time=$(( completion_timestamp - start_timestamp ))

  if [ "$source_size_running" -ne 0 ]; then
    avg_archive_time=$(( ( diff_time / (TAR_VOLUME - 2) ) ))
    remain_time=$(( (avg_archive_time * (archive_volumes - TAR_VOLUME + 2) ) ))
    last_time=$(( completion_timestamp - last_timestamp ))
    dest_size=$(du -c "$bcs_dest"/"$BCS_BASENAME"* | tail -1 | awk '{ print $1 }')
    comp_ratio=$(( 100 - ( ( dest_size * 100) / source_size_running ) ))
  else
    avg_archive_time=0
    remain_time=0
    last_time=0
    dest_size=0
    comp_ratio=0
  fi

  dest_size_text=$(printf "%'.0f" "$dest_size")

# Don't hate me for being ugly
  printf "\
%-${archive_max_name}s \
%${archive_max_num}s \
%4s  \
%-18s \
%-18s \
%-13s \
%-13s \
%-11s \
%-${max_source_size_text}s  \
%-${max_source_size_text}s \
%(%m-%d-%Y %H:%M:%S)T\n" \
    "$TAR_ARCHIVE" \
    "/$archive_volumes" \
    "$(( ( (TAR_VOLUME - 1) * 100) / archive_volumes ))%" \
    "remain..$( Duration_Readable $remain_time )" \
    "elapsed..$( Duration_Readable $diff_time )" \
    "last..$( Duration_Readable $last_time )" \
    "avg..$( Duration_Readable $avg_archive_time )" \
    "compr..${comp_ratio}%" \
    "source..${source_size_running_text}k" \
    "dest..${dest_size_text}k" \
    "$completion_timestamp"
}
