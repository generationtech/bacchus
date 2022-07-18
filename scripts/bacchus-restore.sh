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
#	BCS_SOURCE     - directory location of archive files
#	BCS_DEST       - directory location of archive files
#	BCS_BASENAME   - Base filename for backup archive
#	BCS_VOLUMESIZE - Used LOCALLY here, not from environment
#	BCS_RAMDISK    - Boolean enabling ramdisk
#	BCS_TARDIR     - Intermediate area for tar
#	BCS_DECRYPTDIR - Intermediate area to store unencrypted volume
#	BCS_COMPRESDIR - Intermediate area to store uncompressed volume
#	BCS_COMPRESS   - Boolean enabling compression
# BCS_VERBOSETAR - Tar shows target filenames backed up
# BCS_PASSWORD   - Password to encrypt backup archive volumes
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       Bacchus does not unencrypt backup, and operation will fail if
#       archive was backed up as encrypted

scriptdir=$(dirname "$_")

Cleanup()
{
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

Duration_Readable()
{
  string_date=""

  days=$(( $1/3600/24 ))
  if [ $days -gt 0 ]; then
    string_date+="${days}d"
  fi
  remainder=$(( $1 - (days*3600*24) ))

  hours=$(( remainder/3600 ))
  if [ $hours -gt 0 ]; then
    if [ -n "$string_date" ]; then
      string_date+=":"
    fi
    string_date+="${hours}h"
  fi
  remainder=$(( remainder - (hours*3600) ))

  minutes=$(( remainder/60 ))
  if [ $minutes -gt 0 ]; then
    if [ -n "$string_date" ]; then
      string_date+=":"
    fi
    string_date+="${minutes}m"
  fi
  remainder=$(( remainder - (minutes*60) ))

  if [ $remainder -gt 0 ]; then
    if [ -n "$string_date" ]; then
      string_date+=":"
    fi
    string_date+="${remainder}s"
  fi

  printf "%s" "$string_date"
}

BCS_TMPFILE=$(mktemp -u /tmp/baccus-XXXXXX)
trap Cleanup EXIT

if [ "$BCS_COMPRESS" == "off" ] && [ -z "$BCS_PASSWORD" ]; then
  BCS_TARDIR="$BCS_DEST"
else
  if [ "$BCS_RAMDISK" == "on" ]; then
    source="$BCS_SOURCE"/"$BCS_BASENAME".tar
    ramdisk_size_tmpdir="$BCS_TMPFILE".ramdisk_size
    mkdir "$ramdisk_size_tmpdir"

    if [ "$BCS_COMPRESS" == "on" ]; then
      source="$source".gz
    fi

    if [ -n "$BCS_PASSWORD" ]; then
      if [ "$BCS_COMPRESS" == "on" ]; then
        destination="$ramdisk_size_tmpdir"/"$BCS_BASENAME".tar.gz
      else
        destination="$ramdisk_size_tmpdir"/"$BCS_BASENAME".tar
      fi
      echo "$BCS_PASSWORD" | gpg -qd --batch --cipher-algo AES256 --compress-algo none --passphrase-fd 0 --no-mdc-warning -o "$destination" "$source".gpg
      source="$destination"
    fi

    if [ "$BCS_COMPRESS" == "on" ]; then
      destination="$ramdisk_size_tmpdir"/"$BCS_BASENAME".tar
      pigz -9cd "$source" > "$destination"
      #gzip -9cd "$source" > "$destination"
      source="$destination"
    fi

    BCS_VOLUMESIZE=$(stat -c %s "$source")
    BCS_VOLUMESIZE=$(( BCS_VOLUMESIZE / 1024 ))
    rm -rf "$ramdisk_size_tmpdir"

    ramdisk_size=0
    if [ "$BCS_COMPRESS" == "on" ]; then
      ramdisk_size="$((ramdisk_size + BCS_VOLUMESIZE))"
    fi
    if [ -n "$BCS_PASSWORD" ]; then
      ramdisk_size="$((ramdisk_size + BCS_VOLUMESIZE))"
    fi
    ramdisk_dir="$BCS_TMPFILE".ramdisk
    ramdisk_size="$(( ((ramdisk_size * 1024) + ((BCS_VOLUMESIZE * 1024) / 100)) ))"
    mkdir -p "$ramdisk_dir"
    mount -t tmpfs -o size="$ramdisk_size" tmpfs "$ramdisk_dir"
    BCS_COMPRESDIR="$ramdisk_dir"
    BCS_DECRYPTDIR="$ramdisk_dir"
    BCS_TARDIR="$ramdisk_dir"
  fi
fi

# process first (possibly only) backup volume
echo "$BCS_BASENAME".tar

source="$BCS_SOURCE"/"$BCS_BASENAME".tar
timestamp="$(date +%s)"

if [ "$BCS_COMPRESS" == "on" ]; then
  source="$source".gz
fi

if [ -n "$BCS_PASSWORD" ]; then
  if [ "$BCS_COMPRESS" == "on" ]; then
    destination="$BCS_DECRYPTDIR"/"$BCS_BASENAME".tar.gz
  else
    destination="$BCS_DECRYPTDIR"/"$BCS_BASENAME".tar
  fi
  if [ -z "$source_actual" ]; then
    source_actual=$(stat -c %s "$source".gpg)
    source_actual=$(( source_actual / 1024 ))
  fi
  echo "$BCS_PASSWORD" | gpg -qd --batch --cipher-algo AES256 --compress-algo none --passphrase-fd 0 --no-mdc-warning -o "$destination" "$source".gpg
  source="$destination"
fi

if [ "$BCS_COMPRESS" == "on" ]; then
  destination="$BCS_COMPRESDIR"/"$BCS_BASENAME".tar
  pigz -9cd "$source" > "$destination"
  #gzip -9cd "$source" > "$destination"
  if [ -z "$source_actual" ]; then
    source_actual=$(stat -c %s "$source")
    source_actual=$(( source_actual / 1024 ))
  fi
  if [ -n "$BCS_PASSWORD" ]; then
    rm -f "$source"
  fi
  source="$destination"
fi

if [ -z "$source_actual" ]; then
  source_actual=$(stat -c %s "$source")
  source_actual=$(( source_actual / 1024 ))
fi

dest_actual=$(stat -c %s "$source")
dest_actual=$(( dest_actual / 1024 ))

# Populate external data structure with starting values
export BCS_DATAFILE="$BCS_TMPFILE".runtime
runtime_data=$(jo bcs_source="$BCS_SOURCE" \
                  start_timestamp="$timestamp" \
                  last_timestamp="$timestamp" \
                  source_size_running=$source_actual \
                  dest_size_running=$dest_actual \
                  archive_volumes=1)
echo "$runtime_data" > "$BCS_DATAFILE"

if [ "$BCS_VERBOSETAR" == "on" ]; then
  tarargs='-xpMv'
else
  tarargs='-xpM'
fi

tar "$tarargs" --format posix --new-volume-script "$scriptdir/bacchus-restore-new-volume.sh" --volno-file "$BCS_TMPFILE".volno -f "$source" --directory "$BCS_DEST"

# Pull current runtime data from persistence file
runtime_data=$(<"$BCS_DATAFILE")
bcs_source=$(echo "$runtime_data"          | jq -r '.bcs_source')
start_timestamp=$(echo "$runtime_data"     | jq -r '.start_timestamp')
last_timestamp=$(echo "$runtime_data"      | jq -r '.last_timestamp')
source_size_running=$(echo "$runtime_data" | jq -r '.source_size_running')
dest_size_running=$(echo "$runtime_data"   | jq -r '.dest_size_running')
archive_volumes=$(echo "$runtime_data"     | jq -r '.archive_volumes')

if [ "$BCS_STATISTICS" == "on" ] && [ "$BCS_ENDSTATISTICS" == "on" ]; then
  completion_timestamp="$(date +%s)"
  diff_time=$(( completion_timestamp - start_timestamp ))
  avg_archive_time=$(( ( diff_time / archive_volumes ) ))

  source_size_running_text=$(printf "%'.0f" "$source_size_running")
  dest_size_running_text=$(printf "%'.0f" "$dest_size_running")

  comp_ratio=$(( 100 - ( (source_size_running * 100) / dest_size_running) ))

  printf '\nRESTORE OPERATION COMPLETE\n'
  printf 'Total runtime:                 %s\n' "$( Duration_Readable $diff_time )"
  printf 'Average time per archive file: %s\n' "$( Duration_Readable $avg_archive_time )"
  printf 'Number of archive files:       %s\n' "$archive_volumes"
  printf 'Total space restored:          %sk\n' "$source_size_running_text"
  printf 'Total space on source:         %sk\n' "$dest_size_running_text"
  printf 'Overall compression ratio:     %s%%\n' "$comp_ratio"
fi

vol=$(cat "$BCS_TMPFILE".volno)
case "$vol" in
1)     rm "$source"
       ;;
*)     rm "$source"-"$vol"
esac
