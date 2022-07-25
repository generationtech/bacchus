function Incremental_Stats()
{
  # Compute & output incremntal statistics
  #
  # Make sure these global variable have values before calling this function
  # BCS_BASENAME
  # TAR_VOLUME
  #
  # start_timestamp
  # incremental_timestamp
  # source_size_running
  # dest_size_running

  local archive_max_name
  local max_source_size_text
  local timestamp
  local elapsed_time
  local incremental_time
  local avg_time
  local comp_ratio
  local source_size_running_text
  local dest_size_running_text

  archive_max_name=$(( ${#BCS_BASENAME} + ${#archive_volumes} + 5 ))
  archive_max_num=$(( ${#archive_volumes} + 1 ))

  timestamp=$(date +%s)
  elapsed_time=$(( timestamp - start_timestamp - start_timestamp_running ))
  incremental_time=$(( timestamp - incremental_timestamp - incremental_timestamp_running ))
  avg_time=$(( (elapsed_time / (TAR_VOLUME - 1) ) ))
  remain_time=$(( (avg_time * (archive_volumes - TAR_VOLUME + 1) ) ))

  comp_ratio=$(( 100 - ( (source_size_running * 100) / dest_size_running) ))

  source_size_text=${#source_size_total}
  max_source_size_text=$(( source_size_text + (source_size_text / 3) + 9 ))
  source_size_running_text=$(printf "%'.0f" "$source_size_running")
  echo max_source_size_text $max_source_size_text

  dest_size_running_text=$(printf "%'.0f" "$dest_size_running")

  remain_text=$(Duration_Readable $remain_time)
  remain_text_size=${#remain_text}
  if [ $remain_text_size -gt $remain_text_size_running ]; then
    remain_text_size_running=$remain_text_size
  fi
  remain_text_size=$(( remain_text_size_running + 9 ))

  elapsed_text=$(Duration_Readable $elapsed_time)
  elapsed_text_size=$(( remain_text_size + 1 ))

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

# Don't hate me for being ugly
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
    "$filename" \
    "/$archive_volumes" \
    "$(( ( (TAR_VOLUME) * 100) / archive_volumes ))%" \
    "remain..$remain_text" \
    "elapsed..$elapsed_text" \
    "last..$incremental_time_text" \
    "avg..$avg_text" \
    "compr..${comp_ratio}%" \
    "source..${source_size_running_text}k" \
    "dest..${dest_size_running_text}k" \
    "$timestamp"
}
