#!/bin/bash
#
#	Helper script for multivolume tar restore to unencrypt and uncompress each volume
#
#	Usage:
#	bacchus-restore-new-volume.sh
#
# Utilizes these environment variables:
#	BCS_BASENAME   - Base filename for backup archive
#	BCS_COMPRESS   - Boolean enabling compression
#	BCS_COMPRESDIR - Intermediate area to store uncompressed volume
# BCS_DATAFILE
#	BCS_DECRYPTDIR - Intermediate area to store unencrypted volume
# BCS_ENDSTATISTICS - Enables showing completion statistics
# BCS_PASSWORD   - Password to encrypt backup archive volumes
# BCS_STATISTICS    - Enables showing incremental statistics
# TAR_ARCHIVE
# TAR_FD
# TAR_SUBCOMMAND
# TAR_VOLUME
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       Bacchus does not unencrypt backup, and operation will fail if
#       archive was backed up as encrypted

source "scripts/include/common/duration_readable.sh"  || { echo "scripts/include/common/duration_readable.sh not found";  exit 1; }
source "scripts/include/common/load_persistence.sh"   || { echo "scripts/include/common/load_persistence.sh not found";   exit 1; }
source "scripts/include/restore/incremental_stats.sh" || { echo "scripts/include/restore/incremental_stats.sh not found"; exit 1; }
source "scripts/include/restore/process_volume.sh"    || { echo "scripts/include/restore/process_volume.sh not found";    exit 1; }
source "scripts/include/restore/print_estimate.sh"    || { echo "scripts/include/restore/print_estimate.sh not found";   exit 1; }
source "scripts/include/restore/compute_end.sh"       || { echo "scripts/include/restore/compute_end.sh not found";   exit 1; }

# Pull current runtime data from persistence file
Load_Persistence

tararchivedir=$(dirname "$TAR_ARCHIVE")
name=$(expr "$(basename "$TAR_ARCHIVE")" : '\(.*\)-.*')
vol="${name:-$TAR_ARCHIVE}"-"$TAR_VOLUME"
filename="${vol##*/}"
oldname="${TAR_ARCHIVE##*/}"

while true; do
  source="$bcs_source"/"$filename"
  if [ "$BCS_COMPRESS" == "on" ]; then
    source="$source".gz
    rm -f "$BCS_COMPRESDIR"/"$oldname"
  fi
  if [ -n "$BCS_PASSWORD" ]; then
    source="$source".gpg
    rm -f "$BCS_DECRYPTDIR"/"$oldname"
  fi

  if [ ! -f "$source" ]; then
    stop_timestamp=$(date +%s)
    printf "\nArchive volume: %s\n" "$(basename "$source")"
    printf "NOT FOUND in:   %s\n" "$bcs_source"
    printf "Either place this file in the source directory,\n"
    printf "or enter a new source path here.\n"
    printf "Press enter when ready\n"
    read newpath
    printf "\n"
    if [ -n "$newpath" ]; then
      bcs_source="$newpath"
    fi
  else
    if [ -n "$newpath" ]; then
      unset newpath

      new_source_size=$(du -sk --apparent-size "$bcs_source" | awk '{print $1}')
      source_size_total=$(( source_size_total + new_source_size ))

      new_volumes=$(find "$bcs_source" -name "${BCS_BASENAME}".tar* | wc -l)
      archive_volumes=$(( archive_volumes + new_volumes ))

      if [ "$BCS_ESTIMATE" == "on" ]; then
        printf "UPDATING ESTIMATE..."
        Compute_End
        Print_Estimate
        printf '\n'
      fi

      resume_timestamp=$(date +%s)
      start_timestamp_running=$(( start_timestamp_running + (resume_timestamp - stop_timestamp) ))
      incremental_timestamp_running=$(( incremental_timestamp_running + (resume_timestamp - stop_timestamp) ))
    fi
    break
  fi
done

case "$TAR_SUBCOMMAND" in
  -x) test -r "$source" || exit 1
      ;;
  *)  exit 1
esac

if [ "$BCS_STATISTICS" == "on" ] && [ "$BCS_RUNSTATISTICS" == "on" ]; then
  Incremental_Stats
else
  printf '%s\n' "$filename"
fi

incremental_timestamp=$(date +%s)
source="$bcs_source"/"$filename"
Process_Volume "$filename" "$BCS_DECRYPTDIR" "$BCS_COMPRESDIR"

case "$TAR_FD" in
  none) exit 0
        ;;
  # *)    echo "${name:-$TAR_ARCHIVE}"-"$TAR_VOLUME" >&"$TAR_FD"
  *)    echo "$tararchivedir/$BCS_BASENAME.tar-$TAR_VOLUME" >&"$TAR_FD"
esac

# Update runtime data to persistence file
runtime_data=$(jo bcs_source="$bcs_source" \
                  archive_volumes=$archive_volumes \
                  start_timestamp=$start_timestamp \
                  start_timestamp_running=$start_timestamp_running \
                  incremental_timestamp=$incremental_timestamp \
                  incremental_timestamp_running=0 \
                  remain_text_size_running=$remain_text_size_running \
                  incremental_text_size_running=$incremental_text_size_running \
                  avg_text_size_running=$avg_text_size_running \
                  comp_ratio_text_size_running=$comp_ratio_text_size_running \
                  source_size_total=$source_size_total \
                  source_size_running="$(( source_size_running + source_actual_size ))" \
                  dest_size_running="$(( dest_size_running + dest_actual_size ))" \
                  size_text_running=$size_text_running )
echo "$runtime_data" > "$BCS_DATAFILE"

exit 0
