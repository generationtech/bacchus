#!/bin/bash
function Print_Estimate()
{
  # Print restore estimate based on current values
  #
  # Make sure these global variable have values before calling this function
  # BCS_VOLUMESIZE
  #
  # archive_volumes
  # bcs_volumesize_end
  # source_size_total

  local total_dest_size
  local comp_ratio

  printf "\nVolume size for archive:     %'.0fk\n" "$BCS_VOLUMESIZE"
  printf 'Estimated number of volumes: %s\n' "$archive_volumes"
  printf "Estimated size of source:    %'.0fk\n" "$source_size_total"
  total_dest_size=$(( ( (archive_volumes - 1) * BCS_VOLUMESIZE) + bcs_volumesize_end ))
  printf "Estimated size of restore:   %'.0fk\n" "$total_dest_size"
  comp_ratio=$(( 100 - ( (source_size_total * 100) / total_dest_size) ))
  printf "Estimated compression ratio: %s%%\n" "$comp_ratio"
}
