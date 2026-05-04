#!/bin/bash
function Compute_End()
{
  # Determine actual size of last archive volume at a given location
  #
  # Make sure these global variable have values before calling this function
  # BCS_BASENAME
  # BCS_TMPFILE
  #
  # bcs_source
  # dest_actual_size
  #
  # These variables are set in this function as globals and can
  # be accessed by the caller after completion
  #
  # bcs_volumesize_end

  local ramdisk_size_tmpdir
  local source

  # Determine uncompressed size of last archive volume
  ramdisk_size_tmpdir="$BCS_TMPFILE".ramdisk_size
  mkdir "$ramdisk_size_tmpdir"
  source=$(find "$bcs_source" -name "${BCS_BASENAME}".tar* | sort -V | tail -1)
  source="${source//.gpg/}"
  source="${source//.gz/}"
  Process_Volume "$BCS_BASENAME".tar "$ramdisk_size_tmpdir" "$ramdisk_size_tmpdir"
  bcs_volumesize_end=$dest_actual_size
  rm -rf "$ramdisk_size_tmpdir"
}
