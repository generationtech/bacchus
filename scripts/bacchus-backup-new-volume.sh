#!/bin/bash
#
#	Helper script for multivolume tar backup to compress and encrypt each volume
#
#	Usage:
#	bacchus-backup-new-volume.sh
#
# Utilizes these environment variables:
#	BCS_DATAFILE   - File used to save/retrieve current destination location
#	BCS_COMPRESDIR - Intermediate area to store compressed volume
#	BCS_COMPRESS   - Boolean enabling compression
# BCS_PASSWORD   - Password to encrypt backup archive volumes
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       bacchus does not encrypt backup

# Pull current runtime data from persistence file
runtime_data=$(<"$BCS_DATAFILE")
bcs_dest=$(echo $runtime_data        | jq -r '.bcs_dest')
start_timestamp=$(echo $runtime_data | jq -r '.start_timestamp')
last_timestamp=$(echo $runtime_data  | jq -r '.last_timestamp')
source_size=$(echo $runtime_data     | jq -r '.source_size')
archive_size=$(echo $runtime_data    | jq -r '.archive_size')
archive_volumes=$(echo $runtime_data | jq -r '.archive_volumes')

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
while true; do
  availablespace=$(df -kP "$bcs_dest" | awk '{print $4}' | tail -1)
  lowspace="$(( BCS_VOLUMESIZE * BCS_LOWDISKSPACE ))"
  if [ "$availablespace" -lt "$lowspace" ]; then
    printf "LOW AVAILABLE SPACE on %s (%s < %s)\n" "$bcs_dest" "$availablespace" "$lowspace"
    printf "Either free-up space or swap out storage device and press enter\n"
    printf "Or enter a new destination path and press enter\n"
    read newpath
    printf "\n"
    if [ -n "$newpath" ]; then
      bcs_dest="$newpath"
    fi
  else
    break
  fi
done

# Source and Destination variables flow through following sections
source="$tararchivedir"/"$TAR_ARCHIVE"
destination="$bcs_dest"/"$TAR_ARCHIVE"

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
  none) exit 0
        ;;
  *)    echo "$tarnew" >&"$TAR_FD"
esac

# Compute & output statistics
archive_volume_size=$(stat -c %s "$destination")
archive_size=$(( archive_size + (archive_volume_size / 1024) ))
completion_timestamp="$(date +%s)"

printf '%s of %s (%s%%) remaining(%s) elapsed(%s) last(%s) avg(%s)\n' \
  "$TAR_ARCHIVE" \
  "$archive_volumes" \
  $(( ((TAR_VOLUME - 1) * 100) / archive_volumes )) \
  $(eval "echo $(date -ud "@$(( (($completion_timestamp - $start_timestamp) / (TAR_VOLUME - 1)) * ($archive_volumes - (TAR_VOLUME - 1)) ))" +'$((%s/3600/24))d:%Hh:%Mm:%Ss')") \
  $(eval "echo $(date -ud "@$(( $completion_timestamp - $start_timestamp ))" +'$((%s/3600/24))d:%Hh:%Mm:%Ss')") \
  $(eval "echo $(date -ud "@$(( $completion_timestamp - $last_timestamp ))" +'$((%s/3600/24))d:%Hh:%Mm:%Ss')") \
  $(eval "echo $(date -ud "@$(( ($completion_timestamp - $start_timestamp) / (TAR_VOLUME - 1) ))" +'$((%s/3600/24))d:%Hh:%Mm:%Ss')")

# Update runtime data to persistence file
last_timestamp="$(date +%s)"
runtime_data=$(jo bcs_dest="$bcs_dest" \
                  start_timestamp="$start_timestamp" \
                  last_timestamp="$last_timestamp" \
                  source_size=$source_size \
                  archive_size=$archive_size \
                  archive_volumes=$archive_volumes)
echo "$runtime_data" > "$BCS_DATAFILE"
