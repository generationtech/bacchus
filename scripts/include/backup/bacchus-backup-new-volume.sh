#!/bin/bash
#
#	Helper script for multivolume tar backup to compress and encrypt each volume
#
#	Usage:
#	bacchus-backup-new-volume.sh
#
# Utilizes these environment variables:
# TAR_ARCHIVE
# BCS_BASENAME
#	BCS_COMPRESS   - Boolean enabling compression
#	BCS_COMPRESDIR - Intermediate area to store compressed volume
#	BCS_DATAFILE   - File used to save/retrieve current destination location
# BCS_ENDSTATISTICS - Enables showing completion statistics
# BCS_LOWDISKSPACE
# BCS_PASSWORD   - Password to encrypt backup archive volumes
# BCS_STATISTICS    - Enables showing incremental statistics
# BCS_VOLUMESIZE
# TAR_FD
# TAR_SUBCOMMAND
# TAR_VOLUME
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       bacchus does not encrypt backup

source "scripts/include/common/load_persistence.sh"  || { echo "scripts/include/common/load_persistence.sh not found";  exit 1; }
source "scripts/include/backup/incremental_stats.sh" || { echo "scripts/include/backup/incremental_stats.sh not found"; exit 1; }
source "scripts/include/backup/completion_stats.sh"  || { echo "scripts/include/backup/completion_stats.sh not found";  exit 1; }

# Pull current runtime data from persistence file
Load_Persistence

# Compute new archive volume details
tararchivedir=$(dirname "$TAR_ARCHIVE")
TAR_ARCHIVE=$(basename "$TAR_ARCHIVE")
name=$(expr "$TAR_ARCHIVE" : '\(.*\)-.*')
vol=${name:-"$TAR_ARCHIVE"}-"$TAR_VOLUME"

# Make sure running correct tar subcommand
case "$TAR_SUBCOMMAND" in
  -c)       ;;
  -d|-x|-t) test -r "${name:-$TAR_ARCHIVE}"-"$TAR_VOLUME" || exit 1
            ;;
  *)        exit 1
esac

# Ensure sufficient available free space on target for this archive volume
oldpath=$bcs_dest
while true; do
  availablespace=$(df -kP "$bcs_dest" | awk '{print $4}' | tail -1)
  lowspace="$(( BCS_VOLUMESIZE * BCS_LOWDISKSPACE ))"

  if [ "$availablespace" -lt "$lowspace" ]; then
    stop_timestamp=$(date +%s)
    printf "\nLOW AVAILABLE SPACE on %s (%sk < %sk)\n" "$bcs_dest" "$(printf "%'.0f" "$availablespace")" "$(printf "%'.0f" "$lowspace")"
    printf "Either free-up space, or swap out the storage device,\n"
    printf "or enter a new destination path here.\n"
    printf "Press enter when ready\n"
    read -r newpath
    printf "\n"
    if [ -n "$newpath" ]; then
      bcs_dest="$newpath"
    fi
  else
    if [ -n "$newpath" ]; then
      dest_size_running=$(( dest_size_running + $(du -c --apparent-size "$oldpath" | tail -1 | awk '{ print $1 }') ))

      unset newpath

      resume_timestamp=$(date +%s)
      start_timestamp_running=$(( start_timestamp_running + (resume_timestamp - stop_timestamp) ))
      incremental_timestamp_running=$(( incremental_timestamp_running + (resume_timestamp - stop_timestamp) ))
    fi
    break
  fi
done

if [ "$BCS_STATISTICS" == "on" ] && [ "$BCS_RUNSTATISTICS" == "on" ]; then
  Incremental_Stats
else
  printf '%s\n' "$TAR_ARCHIVE"
fi

# Source and Destination variables flow through following sections
source="$tararchivedir"/"$TAR_ARCHIVE"
destination="$bcs_dest"/"$TAR_ARCHIVE"

archive_source_size=$(du -sk --apparent-size "$source" | awk '{print $1}')
source_size_running=$(( source_size_running + archive_source_size ))

incremental_timestamp=$(date +%s)

# Commpression if enabled
if [ "$BCS_COMPRESS" == "on" ]; then
  if [ -n "$BCS_PASSWORD" ]; then
    destination="$BCS_COMPRESDIR"/"$TAR_ARCHIVE"
  fi
  pigz -9c "$source" > "$destination".gz
  #gzip -9c "$source" > "$destination".gz
  rm -f "$source"
  source="$destination".gz
  destination="$bcs_dest"/"$TAR_ARCHIVE".gz
fi

# Encryption if enabled
if [ -n "$BCS_PASSWORD" ]; then
  destination="$destination".gpg
  echo "$BCS_PASSWORD" | gpg -qc --cipher-algo AES256 --compress-algo none --batch --passphrase-fd 0 -o "$destination" "$source"
  rm -f "$source"
fi

# Update tar archive volume # counter
tarnew="$tararchivedir"/"$vol"
case "$TAR_FD" in
  none) if [ "$BCS_STATISTICS" == "on" ] && [ "$BCS_ENDSTATISTICS" == "on" ]; then
          Completion_Stats
        fi

        exit 0
        ;;

  *)    echo "$tarnew" >&"$TAR_FD"
esac

# Update runtime data to persistence file
runtime_data=$(jo bcs_dest="$bcs_dest" \
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
                  source_size_running=$source_size_running \
                  dest_size_running=$dest_size_running \
                  size_text_running=$size_text_running )
echo "$runtime_data" > "$BCS_DATAFILE"
