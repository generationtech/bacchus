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
  if [[ "$BCS_RAMDISK" == "on" ]]; then
    sync
    umount "$BCS_TMPFILE".ramdisk
    rmdir "$BCS_TMPFILE".ramdisk
  fi
  if [[ "$BCS_TMPFILE" == *"tmp"* ]]; then
    rm -rf "$BCS_TMPFILE"
    rm -rf "$BCS_PATHFILE"
  fi
}

BCS_TMPFILE=$(mktemp -u /tmp/baccus-XXXXXX)
export BCS_PATHFILE="$BCS_TMPFILE".dest
echo "$BCS_SOURCE" > "$BCS_PATHFILE"
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

if [ "$BCS_COMPRESS" == "on" ]; then
  source="$source".gz
fi

if [ -n "$BCS_PASSWORD" ]; then
  if [ "$BCS_COMPRESS" == "on" ]; then
    destination="$BCS_DECRYPTDIR"/"$BCS_BASENAME".tar.gz
  else
    destination="$BCS_DECRYPTDIR"/"$BCS_BASENAME".tar
  fi
  echo "$BCS_PASSWORD" | gpg -qd --batch --cipher-algo AES256 --compress-algo none --passphrase-fd 0 --no-mdc-warning -o "$destination" "$source".gpg
  source="$destination"
fi

if [ "$BCS_COMPRESS" == "on" ]; then
  destination="$BCS_COMPRESDIR"/"$BCS_BASENAME".tar
  pigz -9cd "$source" > "$destination"
  #gzip -9cd "$source" > "$destination"
  if [ -n "$BCS_PASSWORD" ]; then
    rm -f "$source"
  fi
  source="$destination"
fi

if [ "$BCS_VERBOSETAR" == "on" ]; then
  tarargs='-xpMv'
else
  tarargs='-xpM'
fi

tar "$tarargs" --format posix --new-volume-script "$scriptdir/bacchus-restore-new-volume.sh" --volno-file "$BCS_TMPFILE" -f "$source" --directory "$BCS_DEST"

vol=$(cat "$BCS_TMPFILE")
case "$vol" in
1)     rm "$source"
       ;;
*)     rm "$source"-"$vol"
esac
