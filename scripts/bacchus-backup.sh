#!/bin/bash

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
#	bacchus-backup.sh sourcedir basename volumesize compressdir encryptdir
#
#	1 sourcedir   - Directory to backup
#	2 basename    - Base filename for backup archive, appending
#                 incremental backup volume number
#	3 volumesize  - Size of each volume in kB
#	4 compressdir - Intermediate area to store compressed volume
#	5 encryptdir  - Final location to store final volumes
#
# NOTE: If no password is supplied (as BCS_PASSWORD environment var),
#       bacchus does not encrypt backup

scriptdir=$(dirname "$_")
tarimagedir=$(dirname "$2")

sourcedir="$1"
basename="$2"
volumesize="$3"
compressdir="$4"
encryptdir="$5"

if [ $BCS_VERBOSETAR == "on" ]; then
  tarargs='-cpMv'
else
  tarargs='-cpM'
fi

tar "$tarargs" --format=posix --sort=name --new-volume-script "$scriptdir/bacchus-backup-new-volume.sh $compressdir $encryptdir" -L "$volumesize" --volno-file "$tarimagedir"/volume -f "$basename".tar "$sourcedir"

# Setup tar variables to call new-volume script for handling last (or possibly only) archive volume
vol=$(cat "$tarimagedir"/volume)
case "$vol" in
1)     export TAR_ARCHIVE="$basename".tar
       ;;
*)     export TAR_ARCHIVE="$basename".tar-"$vol"
esac

export TAR_VOLUME=$(expr "$vol" + 1)
export TAR_SUBCOMMAND="-c"
export TAR_FD="none"
"$scriptdir"/bacchus-backup-new-volume.sh "$compressdir" "$encryptdir"
rm "$tarimagedir"/volume
printf '\n'
