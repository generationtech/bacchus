#!/bin/bash
#
#	Bacchus restore script
#
#	Restores multi-volume backups, unencrypting, uncompressing, and then untaring.
#	Allows for restoring smaller backups with privacy while allowing
# for partial recovery should any individual incremental archive
# file be damaged.
#
# Other similar solutions using encryption result in total data
# loss of past failed incremental archive file.
#
#	Usage:
#	bacchus-restore.sh
#
# Utilizes these environment variables:
#	BCS_SOURCE     - directory location of archive files
#	BCS_DEST       - directory location of archive files
#	BCS_BASENAME   - base filename for restore archive, appending
#                  incremental archive volume number
#	BCS_DECRYPTDIR - Intermediate area to store unencrypted volume
#	BCS_COMPRESDIR - Intermediate area to store uncompressed volume
# BCS_PASSWORD   - Password to encrypt backup archive volumes
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       Bacchus does not unencrypt backup, and operation will fail if
#       archive was backed up as encrypted

scriptdir=$(dirname "$_")

Cleanup()
{
  if [[ "$BCS_TMPFILE" == *"tmp"* ]]; then
    rm -rf "$BCS_TMPFILE"
  fi
}

BCS_TMPFILE=$(mktemp -u /tmp/baccus-XXXXXX)
trap Cleanup EXIT

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
