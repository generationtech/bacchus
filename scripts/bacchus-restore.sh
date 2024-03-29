#!/bin/bash
#
#	Bacchus restore script
#
#	Restores multi-volume backups, unencrypting, uncompressing, and then untaring.
#	Allows for restoring smaller backups with privacy while allowing
# for partial recovery should any individual incremental archive
# file be damaged.
#
# Other similar solutions using incremental files, compression, and
# encryption result in total data loss past failed incremental archive file.
#
#	Usage:
#	bacchus-restore.sh
#
# Utilizes these environment variables:
#	BCS_BASENAME      - Base filename for backup archive
#	BCS_COMPRESS      - Boolean enabling compression
#	BCS_COMPRESDIR    - Intermediate area to store uncompressed volume
#	BCS_DECRYPTDIR    - Intermediate area to store unencrypted volume
#	BCS_DEST          - directory location of archive files
# BCS_ENDSTATISTICS - Enables showing completion statistics
# BCS_ESTIMATE      - Enables showing estimation info
# BCS_PASSWORD      - Password to encrypt backup archive volumes
#	BCS_RAMDISK       - Boolean enabling ramdisk
#	BCS_SOURCE        - directory location of archive files
# BCS_STATISTICS    - Enables showing incremental statistics
#	BCS_TARDIR        - Intermediate area for tar
# BCS_VERBOSETAR    - Tar shows target filenames backed up
#	BCS_VOLUMESIZE    - Used LOCALLY here, not from environment
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       Bacchus does not unencrypt backup, and operation will fail if
#       archive was backed up as encrypted

scriptdir=$(dirname "$_")

source "scripts/include/common/cleanup.sh"           || { echo "scripts/include/common/cleanup.sh not found";           exit 1; }
source "scripts/include/common/duration_readable.sh" || { echo "scripts/include/common/duration_readable.sh not found"; exit 1; }
source "scripts/include/common/load_persistence.sh"  || { echo "scripts/include/common/load_persistence.sh not found";  exit 1; }
source "scripts/include/restore/completion_stats.sh" || { echo "scripts/include/restore/completion_stats.sh not found"; exit 1; }
source "scripts/include/restore/process_volume.sh"   || { echo "scripts/include/restore/process_volume.sh not found";   exit 1; }
source "scripts/include/restore/print_estimate.sh"   || { echo "scripts/include/restore/print_estimate.sh not found";   exit 1; }
source "scripts/include/restore/compute_end.sh"      || { echo "scripts/include/restore/compute_end.sh not found";   exit 1; }

BCS_TMPFILE=$(mktemp -u /tmp/baccus-XXXXXX)
trap Cleanup EXIT

bcs_source="$BCS_SOURCE"
source=$(find "$bcs_source" -name "${BCS_BASENAME}".tar* | sort | tail -1)

if [[ "$source" == *".gz"*  ]]; then
  BCS_COMPRESS="on"
else
  BCS_COMPRESS="off"
fi

if [[ "$source" != *".gpg"*  ]]; then
  unset BCS_PASSWORD
fi

# Determine max uncompressed size of individual archive volume
ramdisk_size_tmpdir="$BCS_TMPFILE".ramdisk_size
mkdir "$ramdisk_size_tmpdir"
source="$bcs_source"/"$BCS_BASENAME".tar
Process_Volume "$BCS_BASENAME".tar "$ramdisk_size_tmpdir" "$ramdisk_size_tmpdir"
BCS_VOLUMESIZE=$dest_actual_size
rm -rf "$ramdisk_size_tmpdir"

# Setup ramdisk if needed
if [ "$BCS_COMPRESS" == "off" ] && [ -z "$BCS_PASSWORD" ]; then
  BCS_TARDIR="$BCS_DEST"
elif [ "$BCS_RAMDISK" == "on" ]; then
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
  BCS_DECRYPTDIR="$ramdisk_dir"
  BCS_TARDIR="$ramdisk_dir"
fi

# Estimate total restore size and number of archive volumes
archive_volumes=$(find "$bcs_source" -name "${BCS_BASENAME}".tar* | wc -l)
source_size_total=$(du -sk --apparent-size "$bcs_source" | awk '{print $1}')

if [ "$BCS_ESTIMATE" == "on" ]; then
  Compute_End
  Print_Estimate
fi
printf '\n'

# Process first (possibly only) backup volume
archive_max_name=$(( ${#BCS_BASENAME} + ${#archive_volumes} + 5 ))
archive_max_num=$(( ${#archive_volumes} + 1 ))

printf "\
%-${archive_max_name}s \
%${archive_max_num}s \
%4s\n"\
  "${BCS_BASENAME}.tar" \
  "/$archive_volumes" \
  "$(( 100 / archive_volumes ))%"

timestamp=$(date +%s)

source="$bcs_source"/"$BCS_BASENAME".tar
Process_Volume "$BCS_BASENAME".tar "$BCS_DECRYPTDIR" "$BCS_COMPRESDIR"

# Populate external data structure with starting values
export BCS_DATAFILE="$BCS_TMPFILE".runtime
runtime_data=$(jo bcs_source="$bcs_source" \
                  archive_volumes=$archive_volumes \
                  start_timestamp=$timestamp \
                  start_timestamp_running=0 \
                  incremental_timestamp=$timestamp \
                  incremental_timestamp_running=0 \
                  remain_text_size_running=0 \
                  incremental_text_size_running=0 \
                  avg_text_size_running=0 \
                  comp_ratio_text_size_running=0 \
                  source_size_total=$source_size_total \
                  source_size_running=$source_actual_size \
                  dest_size_running=$dest_actual_size \
                  size_text_running=0 )
echo "$runtime_data" > "$BCS_DATAFILE"

if [ "$BCS_VERBOSETAR" == "on" ]; then
  tarargs='-xpMv'
else
  tarargs='-xpM'
fi

tar "$tarargs" --format posix --new-volume-script "$scriptdir/include/restore/bacchus-restore-new-volume.sh" --volno-file "$BCS_TMPFILE".volno -f "$source" --directory "$BCS_DEST"

# Pull current runtime data from persistence file
Load_Persistence

if [ "$BCS_STATISTICS" == "on" ] && [ "$BCS_ENDSTATISTICS" == "on" ]; then
  Completion_Stats
fi

vol=$(cat "$BCS_TMPFILE".volno)
case "$vol" in
1)     rm "$source"
       ;;
*)     rm "$source"-"$vol"
esac
