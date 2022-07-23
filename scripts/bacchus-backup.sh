#!/bin/bash
#
#	Bacchus backup script
#
#	Creates multi-volume backups, first compressing and then encrypting.
#	Allows for creating smaller backups with privacy while allowing
# for partial recovery should any individual incremental archive
# file be damaged.
#
# Other similar solutions using incremental files, compression, and
# encryption result in total data loss past failed incremental archive file.
#
#	Usage:
#	bacchus-backup.sh
#
# Utilizes these environment variables:
#	BCS_SOURCE     - Directory to backup
#	BCS_DEST       - directory location of archive files
#	BCS_BASENAME   - Base filename for backup archive
#	BCS_VOLUMESIZE - Size of each volume in kB
#	BCS_RAMDISK    - Boolean enabling ramdisk
#	BCS_TARDIR     - Intermediate area for tar
#	BCS_COMPRESDIR - Intermediate area to store compressed volume
#	BCS_COMPRESS   - Boolean enabling compression
# BCS_VERBOSETAR - Tar shows target filenames backed up
# BCS_PASSWORD   - Password to encrypt backup archive volumes
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       bacchus does not encrypt backup

scriptdir=$(dirname "$_")

source "scripts/include/common/cleanup.sh" || { echo "scripts/include/common/cleanup.sh not found"; exit 1; }

BCS_TMPFILE=$(mktemp -u /tmp/baccus-XXXXXX)
trap Cleanup EXIT

# Create ramdisk sized based on archive volume size
if [ "$BCS_COMPRESS" == "off" ] && [ -z "$BCS_PASSWORD" ]; then
  BCS_TARDIR="$BCS_DEST"
else
  if [ "$BCS_RAMDISK" == "on" ]; then
    ramdisk_size=0
    if [ "$BCS_COMPRESS" == "on" ]; then
      ramdisk_size="$(( ramdisk_size + BCS_VOLUMESIZE ))"
    fi
    if [ -n "$BCS_PASSWORD" ]; then
      ramdisk_size="$(( ramdisk_size + BCS_VOLUMESIZE ))"
    fi
    ramdisk_dir="$BCS_TMPFILE".ramdisk
    ramdisk_size="$(( ( (ramdisk_size * 1024) + ( (BCS_VOLUMESIZE * 1024) / 100) ) ))"
    mkdir -p "$ramdisk_dir"
    mount -t tmpfs -o size="$ramdisk_size" tmpfs "$ramdisk_dir"
    BCS_COMPRESDIR="$ramdisk_dir"
    BCS_TARDIR="$ramdisk_dir"
  fi
fi

# Estimate total backup size and required archive volumes
if [ "$BCS_ESTIMATE" == "on" ]; then
  printf 'Estimating total size of:  %s\n\n' "$BCS_SOURCE"
  total_source_size=$(du -sk --apparent-size "$BCS_SOURCE" | awk '{print $1}')
  printf "Total size:                %'.0fk\n" "$total_source_size"
  total_volumes=$(( total_source_size / BCS_VOLUMESIZE ))
  if [[ $(( BCS_VOLUMESIZE * total_volumes )) -lt $total_source_size ]]; then
    total_volumes=$(( total_volumes + 1 ))
  fi
  printf "Number of archive volumes: %s (%'.0fk each)\n" "$total_volumes" "$BCS_VOLUMESIZE"
fi
printf '\n'

# Populate external data structure with starting values
export BCS_DATAFILE="$BCS_TMPFILE".runtime
timestamp=$(date +%s)
runtime_data=$(jo bcs_dest="$BCS_DEST" \
                  start_timestamp=$timestamp \
                  start_timestamp_running=0 \
                  incremental_timestamp=$timestamp \
                  incremental_timestamp_running=0 \
                  remain_text_size_running=0 \
                  elapsed_text_size_running=0 \
                  incremental_text_size_running=0 \
                  avg_text_size_running=0 \
                  compr_text_size_running=0 \
                  source_size_total=$total_source_size \
                  source_size_running=0 \
                  dest_size_running=0 \
                  archive_volumes=$total_volumes)
echo "$runtime_data" > "$BCS_DATAFILE"

# Run tar backup
if [ "$BCS_VERBOSETAR" == "on" ]; then
  tarargs='-cpMv'
else
  tarargs='-cpM'
fi
tar "$tarargs" --format=posix --sort=name --new-volume-script "$scriptdir/include/backup/bacchus-backup-new-volume.sh" -L "$BCS_VOLUMESIZE" --volno-file "$BCS_TMPFILE".volno -f "$BCS_TARDIR"/"$BCS_BASENAME".tar "$BCS_SOURCE"

# Setup tar variables to call new-volume script for handling last (or possibly only) archive volume
if [ "$BCS_COMPRESS" == "off" ] && [ -z "$BCS_PASSWORD" ]; then
  Load_Persistence
  BCS_TARDIR="$bcs_dest"
fi
vol=$(cat "$BCS_TMPFILE".volno)
case "$vol" in
  1)  export TAR_ARCHIVE="$BCS_TARDIR"/"$BCS_BASENAME".tar
      ;;
  *)  export TAR_ARCHIVE="$BCS_TARDIR"/"$BCS_BASENAME".tar-"$vol"
esac

export TAR_VOLUME=$(expr "$vol" + 1)
export TAR_SUBCOMMAND="-c"
export TAR_FD="none"
"$scriptdir"/include/backup/bacchus-backup-new-volume.sh
