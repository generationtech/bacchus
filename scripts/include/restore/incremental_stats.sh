#!/bin/bash
function Incremental_Stats()
{
  # Compute & output incremntal statistics
  #
  # Make sure these global variable have values before calling this function
  # BCS_BASENAME
  # TAR_VOLUME
  #
  # archive_volumes
  # avg_text_size_running
  # comp_ratio_text_size_running
  # dest_size_running
  # filename
  # incremental_text_size_running
  # incremental_timestamp
  # incremental_timestamp_running
  # remain_text_size_running
  # size_text_running
  # source_size_running
  # source_size_total
  # start_timestamp
  # start_timestamp_running

  local archive_max_name
  local archive_max_num
  local avg_text
  local avg_text_size
  local avg_time
  local comp_ratio
  local comp_ratio_text
  local comp_ratio_text_size
  local dest_size_running_text
  local dest_size_text_length
  local elapsed_text
  local elapsed_text_size
  local elapsed_time
  local incremental_time
  local incremental_time_text
  local incremental_time_text_size
  local max_dest_size_text
  local max_source_size_text
  local remain_text
  local remain_text_size
  local remain_time
  local source_size_running_text
  local source_size_text_length
  local timestamp

  archive_max_name=$(( ${#BCS_BASENAME} + ${#archive_volumes} + 5 ))
  archive_max_num=$(( ${#archive_volumes} + 1 ))

  timestamp=$(date +%s)
  elapsed_time=$(( timestamp - start_timestamp - start_timestamp_running ))
  incremental_time=$(( timestamp - incremental_timestamp - incremental_timestamp_running ))
  avg_time=$(( (elapsed_time / (TAR_VOLUME - 1) ) ))
  remain_time=$(( (avg_time * (archive_volumes - TAR_VOLUME + 1) ) ))

  comp_ratio=$(( 100 - ( (source_size_running * 100) / dest_size_running) ))

  source_size_text_length=${#source_size_total}
  source_size_running_text=$(printf "%'.0f" "$source_size_running")

  dest_size_text_length=${#dest_size_running}
  dest_size_running_text=$(printf "%'.0f" "$dest_size_running")

  if [ $source_size_text_length -gt $size_text_running ]; then
    size_text_running=$source_size_text_length
  elif [ $dest_size_text_length -gt $size_text_running ]; then
    size_text_running=$dest_size_text_length
  fi
  max_source_size_text=$(( size_text_running + (size_text_running / 3) + 9 ))
  max_dest_size_text=$(( max_source_size_text - 1 ))

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

  comp_ratio_text="$comp_ratio"
  comp_ratio_text_size=${#comp_ratio_text}
  if [ $comp_ratio_text_size -gt $comp_ratio_text_size_running ]; then
    comp_ratio_text_size_running=$comp_ratio_text_size
  fi
  comp_ratio_text_size=$(( comp_ratio_text_size_running + 9 ))

# Don't hate me for being ugly
  printf "\
%-${archive_max_name}s \
%${archive_max_num}s \
%4s  \
%-${remain_text_size}s \
%-${elapsed_text_size}s \
%-${incremental_time_text_size}s \
%-${avg_text_size}s \
%-${comp_ratio_text_size}s \
%-${max_source_size_text}s  \
%-${max_dest_size_text}s \
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
