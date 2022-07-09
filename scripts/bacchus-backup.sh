#!/bin/bash
#
#	Bacchus backup script
#
#	Creates multi-volume backups, first compressing and then encrypting.
#	Allows for creating smaller backups with privacy while allowing
# for partial recovery should any individual incremental archive
# file be damaged.
#
# Other similar solutions using encryption result in total data
# loss past failed incremental archive file.
#
#	usage:
#	bacchus-backup.sh sourcedir destdir basename tardir compressdir volumesize
#
#	1 sourcedir   - Directory to backup
#	2 destdir     - directory location of archive files
#	3 basename    - Base filename for backup archive, appending
#                 incremental backup volume number
#	4 tardir      - Intermediate area for tar
#	5 compressdir - Intermediate area to store compressed volume
#	6 volumesize  - Size of each volume in kB
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       bacchus does not encrypt backup

scriptdir=$(dirname "$_")

sourcedir="$1"
destdir="$2"
basename="$3"
tardir="$4"
compressdir="$5"
volumesize="$6"

Cleanup()
{
  if [[ "$BCS_TMPFILE" == *"tmp"* ]]; then
    rm -rf "$BCS_TMPFILE"
  fi
}

BCS_TMPFILE=$(mktemp -u /tmp/baccus-XXXXXX)
trap Cleanup EXIT

if [ "$BCS_VERBOSETAR" == "on" ]; then
  tarargs='-cpMv'
else
  tarargs='-cpM'
fi

tar "$tarargs" --format=posix --sort=name --new-volume-script "$scriptdir/bacchus-backup-new-volume.sh $destdir $compressdir" -L "$volumesize" --volno-file "$BCS_TMPFILE" -f "$tardir"/"$basename".tar $sourcedir

# Setup tar variables to call new-volume script for handling last (or possibly only) archive volume
vol=$(cat "$BCS_TMPFILE")
case "$vol" in
  1)  export TAR_ARCHIVE="$tardir"/"$basename".tar
      ;;
  *)  export TAR_ARCHIVE="$tardir"/"$basename".tar-"$vol"
esac

export TAR_VOLUME=$(expr "$vol" + 1)
export TAR_SUBCOMMAND="-c"
export TAR_FD="none"
"$scriptdir"/bacchus-backup-new-volume.sh "$destdir" "$compressdir"
printf '\n'
