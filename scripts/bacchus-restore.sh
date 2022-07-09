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
#	NOTE: Execute this script from within the directory you want to
#       put the restored files
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

if [ -n "$BCS_PASSWORD" ]; then
  echo "$BCS_PASSWORD" | gpg -qd --batch --cipher-algo AES256 --compress-algo none --passphrase-fd 0 --no-mdc-warning -o "$decryptdir"/"$basename".tar.gz "$sourcedir"/"$basename".tar.gz.gpg
  compresssource="$decryptdir"
else
  compresssource="$sourcedir"
fi

pigz -9cd "$compresssource"/"$basename".tar.gz > "$compressdir"/"$basename".tar
#gzip -9cd "$compresssource"/"$basename".tar.gz > "$compressdir"/"$basename".tar
if [ -n "$BCS_PASSWORD" ]; then
  rm -f "$decryptdir"/"$basename".tar.gz
fi

if [ "$BCS_VERBOSETAR" == "on" ]; then
  tarargs='-xpMv'
else
  tarargs='-xpM'
fi

tar "$tarargs" --format posix --new-volume-script "$scriptdir/bacchus-restore-new-volume.sh $sourcedir $decryptdir $compressdir" --volno-file "$BCS_TMPFILE" -f "$compressdir"/"$basename".tar --directory "$destdir"

vol=$(cat "$BCS_TMPFILE")
case "$vol" in
1)     rm "$compressdir"/"$basename".tar
       ;;
*)     rm "$compressdir"/"$basename".tar-"$vol"
esac
