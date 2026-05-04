#!/bin/bash
function Cleanup()
{
  # Make sure these global variable have values before calling this function
  # BCS_RAMDISK
  # BCS_TMPFILE

  local ramdisk

  printf "\nOperation shutting down - cleanup process started\n\n"
  if [[ "$BCS_RAMDISK" == "on" ]]; then
    sync
    ramdisk="$BCS_TMPFILE".ramdisk
    if [ "$(findmnt "$ramdisk" -n -o TARGET)" == "$ramdisk" ]; then
      until umount "$BCS_TMPFILE".ramdisk
      do
        sleep 2
        echo "Unmount ramdisk failed, retrying"
      done
    fi
  fi
  if [[ "$BCS_TMPFILE" == *"tmp"* ]]; then
    rm -rf "$BCS_TMPFILE"*
  fi
}
