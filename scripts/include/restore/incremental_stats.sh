function Incremental_Stats()
{
  # Compute & output incremntal statistics
  #
  # Make sure these global variable have values before calling this function
  # BCS_BASENAME
  # TAR_VOLUME
  #
  # start_timestamp
  # last_timestamp
  # source_size_running
  # dest_size_running

  local archive_max_name
  local max_source_size_text
  local incremental_timestamp
  local elapsed_time
  local incremental_time
  local avg_archive_time
  local comp_ratio
  local source_size_running_text
  local dest_size_running_text

  archive_max_name=$(( ${#BCS_BASENAME} + 10 ))
  max_source_size_text=$(( 20 ))

  incremental_timestamp=$(date +%s)
  elapsed_time=$(( incremental_timestamp - start_timestamp - start_timestamp_running ))
  incremental_time=$(( incremental_timestamp - last_timestamp - last_timestamp_running ))
  avg_archive_time=$(( (elapsed_time / (TAR_VOLUME - 1) ) ))

  comp_ratio=$(( 100 - ( (source_size_running * 100) / dest_size_running) ))
  source_size_running_text=$(printf "%'.0f" "$source_size_running")
  dest_size_running_text=$(printf "%'.0f" "$dest_size_running")

# Don't hate me for being ugly
  printf "\
%-${archive_max_name}s \
%-18s \
%-13s \
%-13s \
%-11s \
%-${max_source_size_text}s  \
%-${max_source_size_text}s \
%(%m-%d-%Y %H:%M:%S)T\n" \
    "$filename" \
    "elapsed..$(Duration_Readable $elapsed_time)" \
    "last..$(Duration_Readable $incremental_time)" \
    "avg..$(Duration_Readable $avg_archive_time)" \
    "compr..${comp_ratio}%" \
    "source..${source_size_running_text}k" \
    "dest..${dest_size_running_text}k" \
    "$incremental_timestamp"
}
