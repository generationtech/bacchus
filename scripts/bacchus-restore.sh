#!/bin/bash

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
#	bacchus-restore.sh sourcedir basename compressdir encryptdir
#
#	1 sourcedir - directory location of archive files
#	2 basename - base filename for restore archive, appending
#                     incremental archive volume number
#	3 compressdir - Intermediate area to store uncompressed volume
#	4 encryptdir  - Intermediate area to store unencrypted volume
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       Bacchus does not unencrypt backup, and operation will fail if
#       archive was backed up as encrypted

scriptdir=$(dirname "$_")

sourcedir="$1"
basename="$2"
compressdir="$3"
encryptdir="$4"

# process first (possibly only) backup volume
echo "$basename".tar

if [ -n "$BCS_PASSWORD" ]; then
  rm -f "$encryptdir"/"$basename".tar.gz
  echo "$BCS_PASSWORD" | gpg -qd --batch --cipher-algo AES256 --compress-algo none --passphrase-fd 0 --no-mdc-warning -o "$encryptdir"/"$basename".tar.gz "$sourcedir"/"$basename".tar.gz.gpg
fi

gzip -9cd "$encryptdir"/"$basename".tar.gz > "$compressdir"/"$basename".tar

rm -f "$encryptdir"/"$basename".tar.gz

if [ $BCS_VERBOSETAR == "on" ]; then
  tarargs='-xpMv'
else
  tarargs='-xpM'
fi

tar "$tarargs" --format posix --new-volume-script "$scriptdir/bacchus-restore-new-volume.sh $sourcedir $compressdir $encryptdir" --volno-file volume -f "$compressdir"/"$basename".tar

vol=$(cat volume)
case "$vol" in
1)     rm "$compressdir"/"$basename".tar
       ;;
*)     rm "$compressdir"/"$basename".tar-"$vol"
esac

rm volume
