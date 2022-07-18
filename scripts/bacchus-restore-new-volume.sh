#!/bin/bash
#
#	Helper script for multivolume tar restore to unencrypt and uncompress each volume
#
#	Usage:
#	bacchus-restore-new-volume.sh
#
# Utilizes these environment variables:
#	BCS_SOURCE     - Directory location of archive files
#	BCS_BASENAME   - Base filename for backup archive
#	BCS_DECRYPTDIR - Intermediate area to store unencrypted volume
#	BCS_COMPRESDIR - Intermediate area to store uncompressed volume
#	BCS_COMPRESS   - Boolean enabling compression
# BCS_PASSWORD   - Password to encrypt backup archive volumes
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       Bacchus does not unencrypt backup, and operation will fail if
#       archive was backed up as encrypted

source "scripts/include/common/duration_readable.sh" || { echo "scripts/include/common/duration_readable.sh not found"; exit 1; }
source "scripts/include/common/load_persistence.sh" || { echo "scripts/include/common/load_persistence.sh not found"; exit 1; }
source "scripts/include/restore/incremental_stats.sh" || { echo "scripts/include/restore/incremental_stats.sh not found"; exit 1; }

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
    printf "\nArchive volume %s NOT FOUND in %s\n" "$(basename "$source")" "$bcs_source"
    printf "Either place this file in the source directory and press enter\n"
    printf "Or enter a new source path and press enter\n"
    read newpath
    printf "\n"
    if [ -n "$newpath" ]; then
      bcs_source="$newpath"
    fi
  else
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

last_timestamp="$(date +%s)"

source_actual=$(stat -c %s "$source")
source_actual=$(( source_actual / 1024 ))

if [ -n "$BCS_PASSWORD" ]; then
  if [ "$BCS_COMPRESS" == "on" ]; then
    destination="$BCS_DECRYPTDIR"/"$filename".gz
  else
    destination="$BCS_DECRYPTDIR"/"$filename"
  fi
  echo "$BCS_PASSWORD" | gpg -qd --batch --cipher-algo AES256 --compress-algo none --passphrase-fd 0 --no-mdc-warning -o "$destination" "$source"
  source="$destination"
fi

if [ "$BCS_COMPRESS" == "on" ]; then
  destination="$BCS_COMPRESDIR"/"$filename"
  pigz -9cd "$source" > "$destination"
  #gzip -9cd "$source" > "$destination"
  if [ -n "$BCS_PASSWORD" ]; then
    rm -f "$source"
  fi
  source="$destination"
fi

dest_actual=$(stat -c %s "$source")
dest_actual=$(( dest_actual / 1024 ))

case "$TAR_FD" in
  none) exit 0
        ;;
  # *)    echo "${name:-$TAR_ARCHIVE}"-"$TAR_VOLUME" >&"$TAR_FD"
  *)    echo "$tararchivedir/$BCS_BASENAME.tar-$TAR_VOLUME" >&"$TAR_FD"
esac

# Update runtime data to persistence file
runtime_data=$(jo bcs_source="$bcs_source" \
                  start_timestamp="$start_timestamp" \
                  last_timestamp="$last_timestamp" \
                  source_size_running="$(( source_size_running + source_actual ))" \
                  dest_size_running="$(( dest_size_running + dest_actual ))" \
                  archive_volumes=$(( archive_volumes + 1 )) )
echo "$runtime_data" > "$BCS_DATAFILE"

exit 0
