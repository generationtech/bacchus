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

  source "scripts/include/common/duration_readable.sh" || { echo "scripts/include/common/duration_readable.sh not found"; exit 1; }

  local archive_max_name
  local archive_max_num
  local source_size_text
  local max_source_size_text
  local source_size_running_text
  local elapsed_timestamp
  local elapsed_time
  local avg_time
  local remain_time
  local incremental_time
  local timestamp
  local dest_size
  local comp_ratio
  local dest_size_text

  archive_max_name=$(( ${#BCS_BASENAME} + ${#archive_volumes} + 5 ))
  archive_max_num=$(( ${#archive_volumes} + 1 ))

  timestamp=$(date +%s)
  elapsed_time=$(( timestamp - start_timestamp - start_timestamp_running ))

  if [ "$source_size_running" -ne 0 ]; then
    avg_time=$(( (elapsed_time / (TAR_VOLUME - 2) ) ))
    remain_time=$(( (avg_time * (archive_volumes - TAR_VOLUME + 2) ) ))
    incremental_time=$(( timestamp - incremental_timestamp - incremental_timestamp_running ))

    if compgen -G "${bcs_dest}/${BCS_BASENAME}*" > /dev/null; then
      dest_size=$(( dest_size_running + $(du -c "${bcs_dest}/${BCS_BASENAME}"* | tail -1 | awk '{ print $1 }') ))
    else
      dest_size=$dest_size_running
    fi

    comp_ratio=$(( 100 - ( (dest_size * 100) / source_size_running) ))
  else
    avg_time=0
    remain_time=0
    incremental_time=0
    dest_size=0
    comp_ratio=0
  fi

  remain_text=$(Duration_Readable $remain_time)
  remain_text_size=${#remain_text}
  if [ $remain_text_size -gt $remain_text_size_running ]; then
    remain_text_size_running=$remain_text_size
  fi
  remain_text_size=$(( remain_text_size_running + 9 ))

  elapsed_text=$(Duration_Readable $elapsed_time)
  elapsed_text_size=${#elapsed_text}
  if [ $elapsed_text_size -gt $elapsed_text_size_running ]; then
    elapsed_text_size_running=$elapsed_text_size
  fi
  elapsed_text_size=$(( elapsed_text_size_running + 10 ))

  incremental_time_text=$(Duration_Readable $incremental_time)
  incremental_time_text_size=${#incremental_time_text}
  if [ $incremental_time_text_size -gt $incremental_text_size_running ]; then
    incremental_text_size_running=$incremental_time_text_size
  fi
  incremental_time_text_size=$(( incremental_text_size_running + 7 ))

  avg_text=$(Duration_Readable $avg_time)
  avg_text_size=${#avg_text}
  if [ $avg_text_size -gt $avg_text_size_running ]; then
    avg_text_size_running=$avg_text_size
  fi
  avg_text_size=$(( avg_text_size_running + 6 ))

  compr_text="$comp_ratio"
  compr_text_size=${#compr_text}
  if [ $compr_text_size -gt $compr_text_size_running ]; then
    compr_text_size_running=$compr_text_size
  fi
  compr_text_size=$(( compr_text_size_running + 9 ))

  source_size_text=${#source_size_total}
  max_source_size_text=$(( source_size_text + (source_size_text / 3) + 9 ))
  source_size_running_text=$(printf "%'.0f" "$source_size_running")

  dest_size_text=$(printf "%'.0f" "$dest_size")

# Don't hate me for being ugly
  if [ $incremental_time == 0 ]; then
    printf "\
%-${archive_max_name}s \
%${archive_max_num}s \
%4s\n"  \
    "$TAR_ARCHIVE" \
    "/$archive_volumes" \
    "$(( ( (TAR_VOLUME - 1) * 100) / archive_volumes ))%"
  else
    printf "\
%-${archive_max_name}s \
%${archive_max_num}s \
%4s  \
%-${remain_text_size}s \
%-${elapsed_text_size}s \
%-${incremental_time_text_size}s \
%-${avg_text_size}s \
%-${compr_text_size}s \
%-${max_source_size_text}s  \
%-${max_source_size_text}s \
%(%m-%d-%Y %H:%M:%S)T\n" \
    "$TAR_ARCHIVE" \
    "/$archive_volumes" \
    "$(( ( (TAR_VOLUME - 1) * 100) / archive_volumes ))%" \
    "remain..$remain_text" \
    "elapsed..$elapsed_text" \
    "last..$incremental_time_text" \
    "avg..$avg_text" \
    "compr..$compr_text%" \
    "source..${source_size_running_text}k" \
    "dest..${dest_size_text}k" \
    "$timestamp"
  fi
}
