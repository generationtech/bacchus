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
  # dest_size_running
  # start_timestamp
  # bcs_dest

  local archive_max_name
  local archive_max_num
  local source_size_text
  local max_source_size_text
  local source_size_running_text
  local elapsed_timestamp
  local elapsed_time
  local avg_archive_time
  local remain_time
  local incremental_time
  local dest_size
  local comp_ratio
  local dest_size_text

  archive_max_name=$(( ${#BCS_BASENAME} + ${#archive_volumes} + 5 ))
  archive_max_num=$(( ${#archive_volumes} + 1 ))

  source_size_text=${#source_size_total}
  max_source_size_text=$(( source_size_text + (source_size_text / 3) + 9 ))
  source_size_running_text=$(printf "%'.0f" "$source_size_running")

  incremental_timestamp=$(date +%s)
  elapsed_time=$(( incremental_timestamp - start_timestamp - start_timestamp_running ))

  if [ "$source_size_running" -ne 0 ]; then
    avg_archive_time=$(( ( elapsed_time / (TAR_VOLUME - 2) ) ))
    remain_time=$(( (avg_archive_time * (archive_volumes - TAR_VOLUME + 2) ) ))
    incremental_time=$(( incremental_timestamp - last_timestamp - last_timestamp_running ))

    if compgen -G "${bcs_dest}/${BCS_BASENAME}*" > /dev/null; then
      dest_size=$(( dest_size_running + $(du -c "${bcs_dest}/${BCS_BASENAME}"* | tail -1 | awk '{ print $1 }') ))
    else
      dest_size=$dest_size_running
    fi

    comp_ratio=$(( 100 - ( ( dest_size * 100) / source_size_running ) ))
  else
    avg_archive_time=0
    remain_time=0
    incremental_time=0
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
    "elapsed..$( Duration_Readable $elapsed_time )" \
    "last..$( Duration_Readable $incremental_time )" \
    "avg..$( Duration_Readable $avg_archive_time )" \
    "compr..${comp_ratio}%" \
    "source..${source_size_running_text}k" \
    "dest..${dest_size_text}k" \
    "$incremental_timestamp"
}
