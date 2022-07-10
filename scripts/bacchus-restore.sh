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
#	usage:
#	bacchus-restore.sh sourcedir destdir basename decryptdir compressdir
#
#	1 sourcedir   - directory location of archive files
#	2 destdir     - directory location of archive files
#	3 basename    - base filename for restore archive, appending
#                 incremental archive volume number
#	4 decryptdir  - Intermediate area to store unencrypted volume
#	5 compressdir - Intermediate area to store uncompressed volume
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       Bacchus does not unencrypt backup, and operation will fail if
#       archive was backed up as encrypted

scriptdir=$(dirname "$_")

sourcedir="$1"
destdir="$2"
basename="$3"
decryptdir="$4"
compressdir="$5"

Cleanup()
{
  if [[ "$BCS_TMPFILE" == *"tmp"* ]]; then
    rm -rf "$BCS_TMPFILE"
  fi
}

BCS_TMPFILE=$(mktemp -u /tmp/baccus-XXXXXX)
trap Cleanup EXIT

# process first (possibly only) backup volume
echo "$basename".tar

source="$sourcedir"/"$basename".tar

if [ "$BCS_DISABLECOMPRESS" == "off" ]; then
  source="$source".gz
fi

if [ -n "$BCS_PASSWORD" ]; then
  if [ "$BCS_DISABLECOMPRESS" == "off" ]; then
    destination="$decryptdir"/"$basename".tar.gz
  else
    destination="$decryptdir"/"$basename".tar
  fi
  echo "$BCS_PASSWORD" | gpg -qd --batch --cipher-algo AES256 --compress-algo none --passphrase-fd 0 --no-mdc-warning -o "$destination" "$source".gpg
  source="$destination"
fi

if [ "$BCS_DISABLECOMPRESS" == "off" ]; then
  destination="$compressdir"/"$basename".tar
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

tar "$tarargs" --format posix --new-volume-script "$scriptdir/bacchus-restore-new-volume.sh $sourcedir $decryptdir $compressdir" --volno-file "$BCS_TMPFILE" -f "$source" --directory "$destdir"

vol=$(cat "$BCS_TMPFILE")
case "$vol" in
1)     rm "$source"
       ;;
*)     rm "$source"-"$vol"
esac
